FROM python:3.12.1-slim-bullseye
# So that STDOUT/STDERR is printed
ENV PYTHONUNBUFFERED="1"

# We create the default user and group to run unprivileged
ENV HUNTER_HOME /srv/hunter
WORKDIR ${HUNTER_HOME}

RUN groupadd --gid 8192 hunter && \
    useradd --uid 8192 --shell /bin/false --create-home --no-log-init --gid hunter hunter && \
    chown hunter:hunter ${HUNTER_HOME}

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

# Get poetry package
RUN curl -sSL https://install.python-poetry.org | python3 -
# Adding poetry to PATH
ENV PATH="/root/.local/bin/:$PATH"

RUN git clone https://github.com/datastax-labs/hunter.git ${HUNTER_HOME}

ENV PATH="${HUNTER_HOME}/bin:$PATH"

RUN  --mount=type=ssh \
    virtualenv --python python venv && \
    . venv/bin/activate && \
    poetry install -v && \
    mkdir -p bin && \
    ln -s ../venv/bin/hunter ${HUNTER_HOME}/bin

COPY --chown=hunter:hunter . orion 

RUN . venv/bin/activate && \
    cd orion \
    pip install -r requirements.txt && \
    python setup.py install && \
    ln -s ../venv/bin/orion ${HUNTER_HOME}/bin
