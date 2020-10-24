FROM python:3.8-alpine

COPY ["requirements.txt", "/srv/"]
RUN python3 -m pip install -r /srv/requirements.txt

COPY ["ups-monitor.py", "/srv/"]

ENTRYPOINT ["python3", "/srv/ups-monitor.py"]
CMD ["-o", "--loglevel=INFO", "/etc/monitor.conf"]
