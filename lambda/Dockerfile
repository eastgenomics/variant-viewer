# Lambda Docker image for ingest-handler
# Uses the official AWS Lambda Node.js 20 base image

FROM public.ecr.aws/lambda/nodejs:20

WORKDIR ${LAMBDA_TASK_ROOT}

# Copy package files and install production deps
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev

# Copy compiled Lambda handler and shared libs
# (build step runs: tsc --project tsconfig.lambda.json)
COPY dist/lambda/ ./lambda/
COPY dist/lib/ ./lib/
COPY config/ ./config/

# Lambda handler entrypoint
CMD ["lambda/ingest-handler.handler"]
