FROM bitnami/python:3.6-prod

RUN apt-get update -y --allow-releaseinfo-change
RUN apt-get -y install build-essential sudo postgresql libpq-dev postgresql-client curl \
    postgresql-client-common libncurses5-dev libjpeg-dev zlib1g-dev git wget redis-server && \
    wget -O /usr/local/bin/wait-for-it.sh https://raw.githubusercontent.com/vishnubob/wait-for-it/8ed92e8cab83cfed76ff012ed4a36cef74b28096/wait-for-it.sh && \
    chmod +x /usr/local/bin/wait-for-it.sh

RUN pip install --upgrade pip
COPY ./requirements.txt requirements.txt
RUN pip install --no-cache-dir --use-deprecated=legacy-resolver  -r requirements.txt

RUN curl -sL https://deb.nodesource.com/setup_10.x | sudo -E bash -
RUN apt-get install -y nodejs

COPY ./spiceslp/package.json package.json
RUN npm install

COPY . /code
WORKDIR /code

ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
ENV NODE_PATH=/app/node_modules

ENTRYPOINT [ "wait-for-it.sh", "postgres:5432", "--", "sh", "/code/entrypoint.sh" ]
CMD [ "wait-for-it.sh", "postgres:5432", "--", "supervisord", "-c", "/code/supervisord.conf", "--nodaemon" ]
