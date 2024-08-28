# FROM ubuntu
# FROM python:3.8-slim-buster
FROM jupyter/scipy-notebook

RUN PYTHONPATH=. 

USER root

RUN pip3 --no-cache-dir install notebook papermill papermill[all] numpy matplotlib pandas seaborn scipy 

ADD ./requirements.txt /home/jovyan/requirements.txt
RUN pip3 install -r /home/jovyan/requirements.txt


USER ${NB_UID}

WORKDIR /home/jovyan

ADD ./src /home/jovyan
WORKDIR /home/jovyan

CMD [ "python3", "procserver.py", "-v"]