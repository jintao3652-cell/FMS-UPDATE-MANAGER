FROM mysql:8.4

# We only need the mysqldump client. The base image provides it.
# Add gzip + ca-certs (already there) and our backup script.

COPY backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh

ENTRYPOINT ["/usr/local/bin/backup.sh"]
