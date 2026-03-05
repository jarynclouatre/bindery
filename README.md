# E-Reader Converter (All-in-One)

Automated processing for Kobo and Kindle devices.

### Permissions (PUID/PGID)
This container uses a startup script to map permissions. This ensures the converter can read your files and write the results regardless of which user owns the folders on your host machine. It drops root privileges immediately after the `chown` is complete.

### How to use:
1. Map your `in` and `out` folders in `docker-compose.yml`.
2. Set `PUID` and `PGID` to your host user's ID (type `id` in your server terminal to find them).
3. Access the WebUI at port 5000 to choose your device profile.
