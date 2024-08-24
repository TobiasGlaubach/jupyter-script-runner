
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from JupyRunner.core import schema, db_interface
import yaml



with open('config.yaml', 'r') as fp:
    config = yaml.safe_load(fp)


db_interface.setup(config)

app = FastAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):

    db_interface.start(config)

    yield

    print('END!')



# Get all scripts
@app.get("/scripts")
def get_scripts():
    return db_interface.get_all(schema.Script)


# Get a specific script by ID
@app.get("/scripts/{script_id}")
def get_script(script_id: int):
    obj = db_interface.get(schema.Script, script_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Script not found")
    return obj

# Create a new script
@app.post("/scripts")
def create_script(script: schema.Script):
    return db_interface.add(script)


# Get all devices
@app.get("/devices")
def get_devices():
    return db_interface.get_all(schema.Device)

# Get a specific device by ID
@app.get("/devices/{device_id}")
def get_device(device_id: str):
    obj = db_interface.get(schema.Device, device_id)
    if not obj:
        raise HTTPException(status_code=404, detail="device not found")
    return obj

# Create a new device
@app.post("/devices")
def create_device(device: schema.Device):
    return db_interface.add(device)
    



# Get all data files
@app.get("/datafiles")
def get_datafiles():
    return db_interface.get_all(schema.Device)

# Get a specific data file by ID
@app.get("/datafiles/{datafile_id}")
def get_datafile(datafile_id: int):  # Assuming ID is an integer for datafiles
    obj = db_interface.get(schema.DataFile, datafile_id)
    if not obj:
        raise HTTPException(status_code=404, detail="datafile not found")
    return obj

# Create a new data file
@app.post("/data_files")
def create_data_file(data_file: schema.DataFile):
    return db_interface.add(data_file)


# # Delete a script
# @app.delete("/scripts/{script_id}")
# def delete_script(script_id: int):
#     with Session(engine) as session:
#         script = session.get(Script, script_id)
#         if not script:
#             raise HTTPException(status_code=404, detail="Script not found")
#         session.delete(script)
#         session.commit()
#         return {"message": "Script deleted successfully"}

# # Delete a result
# @app.delete("/results/{result_id}")
# def delete_result(result_id: int):
#     with Session(engine) as session:
#         result = session.get(Result, result_id)
#         if not result:
#             raise HTTPException(status_code=404, detail="Result not found")
#         session.delete(result)
#         session.commit()
#         return {"message": "Result deleted successfully"}

# # Delete a device
# @app.delete("/devices/{device_id}")
# def delete_device(device_id: str):
#     with Session(engine) as session:
#         device = session.get(Device, device_id)
#         if not device:
#             raise HTTPException(status_code=404, detail="Device not found")
#         session.delete(device)
#         session.commit()
#         return {"message": "Device deleted successfully"}

# # Delete a project variable
# @app.delete("/project_variables/{variable_id}")
# def delete_project_variable(variable_id: str):
#     with Session(engine) as session:
#         variable = session.get(ProjectVariable, variable_id)
#         if not variable:
#             raise HTTPException(status_code=404, detail="Project variable not found")
#         session.delete(variable)
#         session.commit()
#         return {"message": "Project variable deleted successfully"}
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)