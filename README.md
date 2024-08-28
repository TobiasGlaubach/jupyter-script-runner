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


3. **Install software by:**

    ```bash
    git pull && docker-compose -f docker-compose.yml build
    ```

6. **Start software** (detached) by (for non detached omit the -d option): 

    ```bash
    docker-compose -f docker-compose.yml up -d
    ```
