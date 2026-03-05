# E-Reader Converter

An automated Docker container for converting comics and ebooks for e-readers. It integrates [Kindle Comic Converter (KCC)](https://github.com/ciromattia/kcc) and [Kepubify](https://github.com/pgaskin/kepubify) with a continuous directory watcher and a WebUI for configuration.

## Features
* **Automated Processing**: Drops files into the input directories; the container detects, processes, and outputs the converted files automatically.
* **WebUI**: Configure all KCC CLI parameters on the fly via a web interface.
* **Failsafes**: Includes file-growth monitoring, processing deduplication, `.failed` appending for errored files, and automatic source cleanup upon successful conversion.
* **Pass-Through**: Ignores already-converted formats (like `.kepub`) to prevent unnecessary processing loops.

## Deployment
Clone the repository and spin up the container using Docker Compose:

```bash
git clone [https://github.com/jarynclouatre/ereader-converter.git](https://github.com/jarynclouatre/ereader-converter.git)
cd ereader-converter
docker-compose up -d
