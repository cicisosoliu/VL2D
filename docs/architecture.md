# VL2D Architecture

VL2D stores metadata in SQLite and large artifacts on the local filesystem. A single worker process polls queued jobs from the database, executes the pipeline, and writes samples for web review. The same core pipeline is shared between CLI and API entry points.

