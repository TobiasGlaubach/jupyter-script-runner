FROM python:3.11-slim-buster

RUN useradd -r --gid=100 --uid=1000 --create-home --shell /bin/bash jovyan

WORKDIR ~


ADD ./requirements.txt /home/jovyan/requirements.txt
RUN pip3 install -r /home/jovyan/requirements.txt


# copy current directory and "./git" to the docker container

RUN chmod 777 -R /home/jovyan
RUN chgrp +100 -R /home/jovyan/

WORKDIR /home/jovyan
USER 1000:100

ADD ./src /home/jovyan

RUN ls -n 
# Expose the port your FastAPI app is listening on (e.g., 8080)
EXPOSE 8080

# Define the command to run when the container starts
# CMD ["uvicorn", "main:app"]
CMD ["fastapi", "run", "main.py", "--port", "8080"]