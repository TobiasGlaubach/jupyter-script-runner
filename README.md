## README.md

**FastAPI Server with SQLModel for Jupyter Script Execution**

This repository contains a FastAPI server that provides RESTful APIs for managing Jupyter scripts, results, devices, and project variables using SQLModel. 

**Prerequisites:**

* Python 3.7 or later
* Conda (optional, but recommended for managing dependencies)

**Installation:**

1. **Create a conda environment (optional):**
   ```bash
   conda create -n jupy_runner python=3.11
   conda activate jupy_runner
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

**Usage:**

1. **Create a database file:**
   * Replace `"sqlite:///your_database.db"` in the `config.yaml` file with your desired database connection string.
   * Create the database file.

2. **Run the server:**
   ```bash
   python main.py
   ```

    OR

    ```bash
    fastapi dev main.py
    ```


**Endpoints:**

* **Scripts:**
  * `GET /scripts`: Get a list of all scripts.
  * `GET /scripts/{script_id}`: Get a specific script by ID.
  * `POST /scripts`: Create a new script.
  * `PATCH /scripts/{script_id}`: Update a script.
* **Results:**
  * `GET /results`: Get a list of all results.
  * `GET /results/{result_id}`: Get a specific result by ID.
  * `POST /results`: Create a new result.
  * `PATCH /results/{result_id}`: Update a result.
* **Devices:**
  * `GET /devices`: Get a list of all devices.
  * `GET /devices/{device_id}`: Get a specific device by ID.
  * `POST /devices`: Create a new device.
  * `PATCH /devices/{device_id}`: Update a device.
* **Project Variables:**
  * `GET /project_variables`: Get a list of all project variables.
  * `GET /project_variables/{variable_id}`: Get a specific project variable by ID.
  * `POST /project_variables`: Create a new project variable.
  * `PATCH /project_variables/{variable_id}`: Update a project variable.

**Customization:**

* **Database:** You can use different databases by modifying the database connection string in `main.py`.
* **Endpoints:** Add or modify endpoints to suit your specific needs.
* **Error handling:** Implement more detailed error handling using HTTPException.
* **Authentication and authorization:** Implement security measures if required.

**Additional Notes:**

* Ensure you have the necessary database driver installed (e.g., `sqlite-utils` for SQLite).
* Replace the placeholder `schema.Device`, `schema.Results`, etc. with your actual class names.
* Customize the endpoints and data structures to match your specific requirements.
