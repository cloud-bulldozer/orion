FROM python:3.11.8-slim-bookworm
# So that STDOUT/STDERR is printed
ENV PYTHONUNBUFFERED="1"

# First let's just get things updated.
# Install System dependencies
RUN apt-get update --assume-yes && \
    apt-get install -o 'Dpkg::Options::=--force-confnew' -y --force-yes -q \
    git \
    openssh-client \
    gcc \
    clang \
    build-essential \
    make \
    curl \
    virtualenv \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="~/bin:$PATH"

RUN python -m venv venv

ADD . orion/

RUN . venv/bin/activate && \
    cd orion \
    pip install setuptools && \
    pip install -r requirements.txt && \
    python setup.py install && \
    ln -s ../venv/bin/orion ~/bin
