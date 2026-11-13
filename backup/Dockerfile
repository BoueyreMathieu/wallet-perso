# Sauvegardes automatiques chiffrées de la base (voir docs/sauvegardes.md).
# Même version de PostgreSQL que la base, pour que pg_dump soit compatible.
FROM postgres:16-alpine
RUN apk add --no-cache age rclone
COPY wallet-backup.sh /usr/local/bin/wallet-backup.sh
# Fins de ligne Unix même si le fichier a été modifié sous Windows.
RUN sed -i 's/\r$//' /usr/local/bin/wallet-backup.sh && chmod +x /usr/local/bin/wallet-backup.sh
ENV RCLONE_CONFIG=/config/rclone/rclone.conf
CMD ["/usr/local/bin/wallet-backup.sh"]
