#!/bin/sh
python /code/manage.py migrate sessions
python /code/manage.py migrate
python /code/manage.py collectstatic --noinput

if [ $SPHERE_DB ]
then
    python /code/manage.py migrate --database=sphere_db
fi
exec "$@"
