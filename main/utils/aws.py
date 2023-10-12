import boto3, os
from boto3.s3.transfer import S3Transfer
from oauth2client.service_account import ServiceAccountCredentials
from django.conf import settings
from main.models import Media, TelegramGroup
import requests
from PIL import Image
import os, logging

logger = logging.getLogger(__name__)

class AWS(object):
    
    def __init__(self):
        json_creds = os.path.join(settings.BASE_DIR, 'spice-slp-token-e17e0c3bb681.json')
        credentials = ServiceAccountCredentials.from_json_keyfile_name(json_creds)
        credentials = { 
            'aws_access_key_id':settings.AWS_ACCESS_KEY_ID ,
            'aws_secret_access_key': settings.AWS_SECRET_ACCESS_KEY
        }
        self.client = boto3.client('s3', 'us-west-2', **credentials)
        self.bucket = settings.AWS_BUCKET_NAME

    def upload(self, fname):
        transfer = S3Transfer(self.client)
        transfer.upload_file('/tmp/' + fname, self.bucket, fname, extra_args={'ACL': 'public-read'})
        bucket_location = self.client.get_bucket_location(Bucket=self.bucket) 
        return "https://s3-{0}.amazonaws.com/{1}/{2}".format( 
            bucket_location['LocationConstraint'], 
            self.bucket, 
            fname
        ) 

    def process_object(self, title, field, objects, counter=1):
        total = objects.count()
        for _obj in objects:
            download_url = str(getattr(_obj, field))
            file_type = download_url.split('.')[-1]
            file_id = download_url.split('.')[-2].split('/')[-1]
            if file_type == 'jpg':
                r = requests.get(download_url)
                temp_name = '/tmp/' + file_id + '-temp' + '.jpg'
                filename = '/tmp/' + file_id + '.jpg'
                with open(temp_name, 'wb') as f:
                    f.write(r.content)
                try:
                    im = Image.open(temp_name).convert("RGB")
                    im.save(filename,"jpeg")
                except OSError as exc:
                    if "cannot identify image file" in str(exc):
                        continue
                    raise OSError(exc)
                os.remove(temp_name)
                fname = file_id + '.jpg'
            elif file_type == 'png':
                try:
                    img = Image.open(requests.get(download_url, stream=True).raw)
                    img.save('/tmp/' + file_id + '.png', 'png')
                except OSError as exc:
                    expected_errors = [
                        "broken PNG file",
                        "image file is truncated",
                        "cannot identify image file"
                    ]
                    persist = False
                    for error in expected_errors:
                        if  error in str(exc):
                            persist = True
                    if persist: continue
                    raise OSError(exc)
                fname = file_id + '.png'

            elif file_type == 'mp4':
                # Download video
                r = requests.get(download_url)
                with open('/tmp/' + file_id + '.mp4', 'wb') as f:
                    f.write(r.content)
                fname = file_id + '.mp4'

            else:
                # Other objects
                ext = download_url.split('.')[-1]
                r = requests.get(download_url)
                with open('/tmp/' + file_id + '.' + ext, 'wb') as f:
                    f.write(r.content)
                fname = file_id + '.' + ext

            # Upload obj file to AWS
            aws_url = self.upload(fname)

            # After uploading delete the file
            os.remove('/tmp/' + fname)

            setattr(_obj, field, aws_url)
            _obj.save()
            logger.info(f'AWS MIGRATION {title.upper()}: {counter} out of {total} | {fname}')
            counter += 1

    def migrate_spicebot_profile_pic(self):
        objects = TelegramGroup.objects.exclude(profile_pic_url='').filter(aws_profile_pic_url='')
        self.process_object('spicebot profile pic', 'profile_pic_url', objects)
        
    def migrate_spicebot_media(self):
        objects = Media.objects.filter(aws_url='')
        self.process_object('spicebot media', 'url' , objects)