## README.md

**Web Based Jupyter Script Execution and managing metadata in a database**

This repository contains a software with a webpage frontent to run Jupyter scripts parameterized and save the result (metadata) in an automated way in a database

The server runs as a FastAPI server that provides RESTful APIs for managing Jupyter scripts, results, devices, and project variables using SQLModel. 

## URLs: 
* Web-UI: http://localhost:7990/ui
* Basic starting page: http://localhost:7990
* Jupyter-lab: http://localhost:7991/lab
    * login token: jupyrun
* Database und API Dokumentation: http://localhost:7990/docs


## Prerequisites:

* Python 3.7 or later
* Conda (optional, but recommended for managing dependencies)

## Installation:

1. **Create a conda environment (optional):**
   ```bash
   conda create -n jupy_runner python=3.11
   conda activate jupy_runner
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Configuration:

1. **config.yaml**
   * NOTE: If you are deploying via docker the pathes as they are should work and you can skip this step. Replace the pathes in the `config.yaml` file with your desired database connection and folder locations (hint: best use only forward slashes no matter the env). 

2. **docker-compose.yml**
    * if necessary replace the pathes '/var/jupyrun/db' and '/var/jupyrun/shared' with whatever path you want to save the database and scripts at.
    * if you want replace the ports for the two servers as you see fit

3. **permissions**
    * If you are facing issues with write permissions for the path you want to use for storing the database and scripts at you **can** grant total access rights to the folder where you want to database and scripts to be stored by typing (assumes /var/jupyrun is your folder path): `chmod -R 777 /var/jupyrun` 
    * **WARNING!!!** grants access to folder to all users! 
    * NOTE: needs root privileges
    

    
4. **NOTE for administration / docker user info:**
    * In case you need to do any administration here is some info on the users inside the docker containers. 
    * As can be seen in the deploy/main/Dockerfile and deploy/procserver/Dockerfile files the scrips always run as the default jupyter user called `jovyan` with home dir `/home/jovyan` and `uid=1000` and `gid=100`.




## Running as dev:

to run the server for development locally:

1. **Run the server:**
   ```bash
   python main.py
   ```

    OR

    ```bash
    fastapi dev main.py
    ```

2. **Run the Scriptrunner**

* start the scriptrunner to run only **once** in debug mode and return after 
   ```bash
   python scriptrunner.py debug
   ```

* start the scriptrunner to run **indefinitely**

    ```bash
    fastapi dev main.py
    ```


## Deploy

NOTE: Newer versions of docker need `docker compose` instead of `docker-compose`

1. **Update**

    ```bash
    git pull
    ```

2. **Build**
    


    ```bash
    docker-compose -f docker-compose.yml build
    ```

3. **Start software** (detached) by (for non detached omit the -d option): 

    ```bash
    docker-compose -f docker-compose.yml up -d
    ```


## Deploy oneliner


copy paste this:


    ```bash
    dit pull && docker-compose -f docker-compose.yml build && docker-compose -f docker-compose.yml up -d
    ```

