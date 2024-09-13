# FROM ubuntu
# FROM python:3.8-slim-buster
# FROM jupyter/scipy-notebook
FROM jupyter/scipy-notebook

RUN PYTHONPATH=. 

USER root
RUN apt-get update && apt-get install pandoc -y



# ply and future are needed for katcp
RUN pip3 --no-cache-dir install notebook papermill papermill[all] numpy matplotlib pandas seaborn scipy ply future
RUN pip3 install pyopenssl --upgrade

ADD ./requirements.txt /home/jovyan/requirements.txt
RUN pip3 install -r /home/jovyan/requirements.txt

ADD ./src /home/jovyan

ENV PYTHONPATH /home/jovyan

RUN chmod -R 777 /home/jovyan
WORKDIR /home/jovyan
USER ${NB_UID}


# CMD [ "python3", "procserver.py", "-v"]