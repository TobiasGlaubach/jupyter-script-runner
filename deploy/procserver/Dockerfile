# FROM ubuntu
# FROM python:3.8-slim-buster
FROM jupyter/scipy-notebook

RUN PYTHONPATH=. 

RUN pip3 --no-cache-dir install notebook papermill papermill[all] numpy matplotlib pandas seaborn scipy 


RUN chmod -R 777 /home/jovyan

USER ${NB_UID}

WORKDIR /home/jovyan


ADD ./requirements.txt /home/jovyan/requirements.txt
RUN chmod -R 777 /home/jovyan

RUN pip3 install -r /home/jovyan/requirements.txt

ADD ./src /home/jovyan
WORKDIR /home/jovyan

CMD [ "python3", "procserver.py", "-v"]