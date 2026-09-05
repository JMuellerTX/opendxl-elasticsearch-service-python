# Base image from Python 3.13 (slim)
FROM python:3.13-slim

VOLUME ["/opt/dxlelasticsearchservice-config"]

# Copy application files
COPY . /tmp/build
WORKDIR /tmp/build

# Clean application
RUN python ./clean.py

# Install application and its dependencies.
# - dxlbootstrap 0.2.x still imports pkg_resources, which setuptools >= 82 no
#   longer ships
# - the dxlclient release on PyPI pins msgpack<1.0.0 (GHSA-6v7p-g79w-8964);
#   install the fixed client from the fork before the application pulls it in
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && pip install --no-cache-dir "setuptools<82" \
        "dxlclient @ git+https://github.com/derjochenmueller/opendxl-client-python@epo-legacy" \
    && pip install --no-cache-dir . \
    && apt-get purge -y --auto-remove git \
    && rm -rf /var/lib/apt/lists/*

# Cleanup build
RUN rm -rf /tmp/build

################### INSTALLATION END #######################
#
# Run the application.
#
# NOTE: The configuration files for the application must be
#       mapped to the path: /opt/dxlelasticsearchservice-config
#
# For example, specify a "-v" argument to the run command
# to mount a directory on the host as a data volume:
#
#   -v /host/dir/to/config:/opt/dxlelasticsearchservice-config
#
CMD ["python", "-m", "dxlelasticsearchservice", "/opt/dxlelasticsearchservice-config"]
