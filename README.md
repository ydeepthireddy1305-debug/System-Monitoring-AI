# System Monitoring with AI Predictions

I built this project using Python and React to monitor system resource usage and view alerts in one place. I used FastAPI for the backend and MySQL to store monitoring data. I also worked on adding machine learning and AI-based incident analysis to the monitoring workflow.

## Features

- Collects CPU, RAM, and disk usage using psutil.
- Displays system metrics and resource usage through a React dashboard.
- Detects unusual system activity using a machine learning pipeline.
- Generates failure-risk scores based on monitoring data.
- Uses the Google Gemini API to assist with incident analysis.
- Includes JWT authentication and role-based access control.
- Records remediation actions and checks recovery status.

## Screenshots

### Monitoring Dashboard

The dashboard displays current resource usage, failure risk, incident counts, detected anomalies, and remediation statistics.

![Monitoring Dashboard](dashboard.png)

### Backend Deployment

The FastAPI backend is deployed as a Docker-based service on Render.

![Backend Deployment](deployment.png)


### Database

I used MySQL to store the monitoring data. This screenshot shows the database service configured in Aiven.
![MySQL Database](database.png)

## Technologies Used

- Python
- FastAPI
- React
- MySQL
- psutil
- scikit-learn
- NumPy and pandas
- Google Gemini API
- JWT authentication
- Docker
- Render
- Git and GitHub
- pytest

## Run Locally

### 1. Clone the Repository

```bash
git clone https://github.com/ydeepthireddy1305-debug/System-Monitoring-AI.git
cd System-Monitoring-AI
```

### 2. Create a Python Virtual Environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

Install the required Python packages using the project's `requirements.txt` file.

### 4. Configure Environment Variables

Configure the required environment variables for the MySQL database connection, JWT secret, and Gemini API key. Keep passwords and API keys private.

### 5. Start the Application

Start the FastAPI backend using its configured entry point. In a separate terminal, navigate to the `frontend` directory, install the frontend dependencies, and start the React development server using the script defined in `package.json`.

The backend API documentation is available at `/docs` when the server is running.
## Tests

I used pytest to check the backend functionality. Run the tests from the appropriate project directory:

```bash
python -m pytest -q
```

## Project Links

GitHub: https://github.com/ydeepthireddy1305-debug/System-Monitoring-AI

Live application: https://system-monitoring-ai.onrender.com
