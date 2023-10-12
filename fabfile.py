from functools import wraps
from fabric.api import env, run
from fabric.contrib.project import rsync_project
from fabric.context_managers import cd
import os

from dotenv import dotenv_values
config = dotenv_values(".env")

project = 'spicebot'

def staging():
    env['server'] = 'staging'
    env.hosts = [config['STAGING']]
    env.user = 'root'


def prod():    
    env['server'] = 'prod'
    env.hosts = [config['PROD']]
    env.user = 'root'


def uname():
    run('uname -a')


def sync():
    exc=[
            '.venv',
            '.venv2',
            '.git',
            'static',
            '.DS_Store',
            '.env',
            '__pycache__',
            '*.pyc',
            '*.log',
            '*.pid',
            'celerybeat-schedule*',
            'node_modules'
        ]
    rsync_project('/root', delete=False, exclude=exc, 
        ssh_opts='-o stricthostkeychecking=no')



def build():
    project_dir = os.path.join('/root', project)
    with cd(project_dir):
        run('docker-compose -p %s -f compose/%s/setup.yml build' % (project, env['server']))



def up():
    project_dir = os.path.join('/root', project)
    with cd(project_dir):
        run('docker-compose -p %s -f compose/%s/setup.yml up -d' % (project, env['server']))



def down():
    project_dir = os.path.join('/root', project)
    with cd(project_dir):
        run('docker-compose -p %s -f compose/%s/setup.yml down' % (project, env['server']))



def nginx():
    project_dir = os.path.join('/root', project)
    with cd(project_dir):
        nginx_conf = "/etc/nginx/sites-available/%s" % project
        nginx_slink = "/etc/nginx/sites-enabled/%s" % project
        run('sudo rm %s' % nginx_conf)
        run('sudo rm %s' % nginx_slink)
        run('sudo cat compose/%s/nginx.conf > %s' % (env['server'], nginx_conf))
        run('sudo ln -s %s %s' % (nginx_conf, nginx_slink))
        run('sudo service nginx restart')



def deploy():
    sync()
    build()
    down()
    up()
    


def logs():
    project_dir = os.path.join('/root', project)
    with cd(project_dir):
        run('docker-compose -p %s -f compose/%s/setup.yml logs  -f web' % (project, env['server']))

