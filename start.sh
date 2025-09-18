#!/bin/bash

echo "🚀 Starting Borgitory with HTTP on port 8000"
exec borgitory serve --host 0.0.0.0 --port 8000