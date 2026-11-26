# Q-SmartStroke

The ZIP includes the React frontend, FastAPI backend, model training code, Excel
activity logging and a Dockerfile that serves the app and API on one port.

## Run the publishing package locally

1. Extract the complete ZIP. The Kaggle CSV is included under data/raw.
2. From the extracted project folder, run:

   ```powershell
   docker build -t q-smartstroke .
   docker run --rm -p 127.0.0.1:8000:8000 --mount "type=volume,source=q-smartstroke-state,target=/app/state" q-smartstroke
   ```

3. Wait for "Application startup complete". Open http://127.0.0.1:8000/.
   Check http://127.0.0.1:8000/api/health for the dataset source and record count.
4. The server creates its own workbook. The Docker volume retains it after
   container replacement. View Model_Benchmarks and Interaction_Telemetry
   under Research Lab or download the workbook from the app.

For a demonstration without the Kaggle CSV, use the same Docker run command
with -e Q_SMARTSTROKE_DATA_MODE=demo. Start that
demo with a different volume name to keep its workbook separate.

## Publish on a Docker-capable host

Build from the root Dockerfile. The process listens on PORT (default 8000).
The Dockerfile copies the included Kaggle CSV into the image. Set
Q_SMARTSTROKE_DATA_MODE=kaggle to use it. Mount persistent writable storage
at /app/state. Run one worker and one
replica for Excel persistence. Give the service time to train before marking
it ready.

Use HTTPS and restrict the app to your research/demo audience. The experiment
includes dataset upload, workbook download and shared activity/progress controls.
Use host authentication or set both Q_SMARTSTROKE_WEB_USER and
Q_SMARTSTROKE_WEB_PASSWORD as deployment secrets for a shared browser sign-in.
If using the built-in sign-in, configure health checks with credentials or use
a TCP readiness check and verify /api/health after login.

Dataset source: https://www.kaggle.com/datasets/fedesoriano/stroke-prediction-dataset

Keep local workbooks and deployment credentials out of your source repository. App outputs are for research and fictional demos.
