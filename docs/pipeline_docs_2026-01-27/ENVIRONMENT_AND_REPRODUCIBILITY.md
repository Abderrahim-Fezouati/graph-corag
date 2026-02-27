# Environment and Reproducibility

## Environment
- Conda env: `gcorag-lite-cu118`
- Python: 3.11.13

## GPU / CUDA assumptions
- CUDA-capable NVIDIA GPU assumed.
- Torch build in this env is expected to be CUDA 11.8 compatible.

## Editable install requirement
The repo uses a src-layout. Install in editable mode to enable `import graphcorag` without PYTHONPATH:
```
C:\Users\Abdou\miniconda3\envs\gcorag-lite-cu118\python.exe -m pip install -e .
```

## Running with explicit Python
If conda activation is unreliable on Windows, use the env python directly:
```
C:\Users\Abdou\miniconda3\envs\gcorag-lite-cu118\python.exe <script> [args]
```

## Moving to a server
1) Copy the repo to the server.
2) Create the conda env with matching Python (3.11.x).
3) Install dependencies and models.
4) Run `python -m pip install -e .` in the repo root.
5) Confirm model directories (`models/`) and data files are present.

## Logging and output directories
- Use `.tmp/` for intermediate artifacts and diagnostics.
- Use a dedicated run folder for outputs, e.g.:
  - `runs/<timestamp>_smoke/outputs`
  - `runs/<timestamp>_smoke/logs`
- Redirect stdout/stderr for reproducibility:
```
... 1> runs\<timestamp>_smoke\logs\stage.stdout.txt 2> runs\<timestamp>_smoke\logs\stage.stderr.txt
```
