from fastapi import FastAPI, HTTPException
from sqlmodel import Session, create_engine, SQLModel, select
from JupyRunner.core import schema
import yaml

with open('config.yaml', 'r') as fp:
    config = yaml.safe_load(fp)


sqlite_file_name = config.get('db', {})['filepath']
sqlite_url = f"sqlite:///{sqlite_file_name}"
connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, echo=True, connect_args=connect_args)


app = FastAPI()

@app.on_event("startup")
def create_tables():
    SQLModel.metadata.create_all(engine)



# Get all scripts
@app.get("/scripts")
def get_scripts():
    with Session(engine) as session:
        return session.exec(select(schema.Script)).all()

# Get a specific script by ID
@app.get("/scripts/{script_id}")
def get_script(script_id: int):
    with Session(engine) as session:
        script = session.get(schema.Script, script_id)
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")
        return script

# Create a new script
@app.post("/scripts")
def create_script(script: schema.Script):
    with Session(engine) as session:
        session.add(script)
        session.commit()
        session.refresh(script)
        return script

# # Update a script
# @app.patch("/scripts/{script_id}")
# def update_script(script_id: int, script: schema.Script):
#     with Session(engine) as session:
#         db_script = session.get(schema.Script, script_id)
#         if not db_script:
#             raise HTTPException(status_code=404, detail="Script not found")
#         db_script.script_name = script.script_name
#         # ... update other fields as needed
#         session.commit()
#         return db_script
    

# Get all devices
@app.get("/devices")
def get_devices():
    with Session(engine) as session:
        return session.exec(select(schema.Device)).all()

# Get a specific device by ID
@app.get("/devices/{device_id}")
def get_device(device_id: str):
    with Session(engine) as session:
        device = session.get(schema.Device, device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return device

# Create a new device
@app.post("/devices")
def create_device(device: schema.Device):
    with Session(engine) as session:
        session.add(device)
        session.commit()
        session.refresh(device)
        return device
    

# Get all data files
@app.get("/data_files")
def get_data_files():
    with Session(engine) as session:
        return session.exec(select(schema.DataFile)).all()
    
# Get a specific data file by ID
@app.get("/data_files/{data_file_id}")
def get_data_file(data_file_id: int):  # Assuming ID is an integer for data_files
    with Session(engine) as session:
        data_file = session.get(schema.DataFile, data_file_id)
        if not data_file:
            raise HTTPException(status_code=404, detail="Data file not found")
        return data_file

# Create a new data file
@app.post("/data_files")
def create_data_file(data_file: schema.DataFile):
    with Session(engine) as session:
        session.add(data_file)
        session.commit()
        session.refresh(data_file)
        return data_file


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