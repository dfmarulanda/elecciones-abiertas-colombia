FROM python:3.13-slim

WORKDIR /app
COPY apps/api /app/apps/api
COPY data/manifests/historical-2018-mmv-context-v2-c456aeb032917d5c.json /app/data/manifests/
COPY data/manifests/historical-2022-mmv-context-v2-288e9b41c14730e9.json /app/data/manifests/
COPY data/releases/historical-2018-mmv-context-v2-c456aeb032917d5c /app/data/releases/historical-2018-mmv-context-v2-c456aeb032917d5c
COPY data/releases/historical-2022-mmv-context-v2-288e9b41c14730e9 /app/data/releases/historical-2022-mmv-context-v2-288e9b41c14730e9
COPY packages/contracts/openapi.json /app/packages/contracts/openapi.json
ENV ELECCIONES_OPENAPI_PATH=/app/packages/contracts/openapi.json
ENV HISTORICAL_DATA_PATH=/app/data
ENV PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir /app/apps/api
RUN addgroup --system elecciones && adduser --system --ingroup elecciones --no-create-home elecciones
# Verify the pinned Parquet sources, then derive compact geography/category
# indexes and summary counts. Downloadable bytes remain the original Parquet.
RUN python -c "from pathlib import Path; from elecciones_api.historical_repository import HistoricalDuckDBRepository; releases=('historical-2018-mmv-context-v2-c456aeb032917d5c','historical-2022-mmv-context-v2-288e9b41c14730e9'); repository=HistoricalDuckDBRepository(Path('/app/data'), releases, releases[1]); repository.build_geography_read_model(Path('/app/data/historical-geography.duckdb'))"
# The checked-in release files are deliberately 0600 on the host. Keep their
# bytes root-owned and immutable in the image, but make the packaged read model
# traversable/readable by the non-root API process.
RUN find /app/data -type d -exec chmod 0555 {} + \
    && find /app/data -type f -exec chmod 0444 {} + \
    && chmod 0444 /app/packages/contracts/openapi.json
USER elecciones
# Build fails closed unless the runtime identity can open the index read-only
# and fully revalidate its source hashes, keysets, row counts, and served fields.
RUN python -c "from pathlib import Path; from elecciones_api.historical_repository import HistoricalDuckDBRepository; releases=('historical-2018-mmv-context-v2-c456aeb032917d5c','historical-2022-mmv-context-v2-288e9b41c14730e9'); HistoricalDuckDBRepository(Path('/app/data'), releases, releases[1])"
EXPOSE 8000
CMD ["uvicorn", "elecciones_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
