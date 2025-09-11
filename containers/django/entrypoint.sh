#!/bin/sh
# When you change this file, please rebuild the docker image.

python manage.py makemigrations --noinput
python manage.py migrate --noinput --verbosity 2 # set verbosity to 2 for more detailed output

# added for debugging
python manage.py makemigrations sortIT
python manage.py migrate sortIT --noinput --verbosity 2
# python manage.py showmigrations sortIT

echo "DEBUG: $DEBUG"

if [ "$DEBUG" = "True" ]; then
    echo "DEBUG mode: skipping collectstatic"
else
    echo "Production mode: running collectstatic"
    python manage.py collectstatic --noinput
fi

# if the superuser does not exist in the database, create it
if [ -z "$(python manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists()")" ]; then
    python manage.py createsuperuser --noinput
    echo "Superuser created."
fi

if [ "$DEBUG" = "True" ]; then
    echo "Starting development server..."
    python manage.py runserver 0.0.0.0:8000
else
    echo "Starting production server..."
    gunicorn -c gunicorn_config.py --workers 4 --bind 0.0.0.0:8000 djangopj.wsgi:application
fi
