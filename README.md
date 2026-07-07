# GalleryForge

GalleryForge is an automated publishing pipeline for AI-generated media.

It monitors incoming assets, registers them in a database, generates thumbnails, builds release packages, and creates ready-to-publish galleries with structured metadata. The project is designed to work alongside ComfyUI and to integrate with publishing and automation tools such as MemuBot.

## Features

* Automatic asset ingestion
* SHA-256 duplicate detection
* SQLite asset registry
* Image and video thumbnail generation
* Release management
* Static HTML gallery generation
* JSON release metadata
* MemuBot integration
* Git-based development workflow

## Project Pipeline

```text
ComfyUI
    │
    ▼
assets/inbox
    │
    ▼
watcher.py
    │
    ▼
asset_registry.py
    │
    ▼
process_new_assets.py
    │
    ▼
thumbnailer.py
    │
    ▼
release_manager.py
    │
    ▼
gallery_builder.py
    │
    ├── index.html
    ├── release.json
    ├── images/
    └── thumbnails/
            │
            ▼
memubot_connector.py
```

## Current Status

Current development includes:

* ✅ Asset registry
* ✅ SHA-256 duplicate detection
* ✅ SQLite database
* ✅ Image thumbnail generation
* ✅ Video thumbnail generation
* ✅ Release packaging
* ✅ HTML gallery generation
* ✅ Release metadata (JSON)
* ✅ MemuBot connector

Planned features:

* Gallery themes
* Tagging and metadata management
* Search and filtering
* Patreon exporter
* DeviantArt exporter
* Telegram publishing
* Additional automation connectors

## License

This project is currently under active development.
