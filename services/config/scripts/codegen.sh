#!/bin/sh
set -e

OUT_DIR=${OUT_DIR:-/app/configapp/grpc_gen}
PROTO_DIR=${PROTO_DIR:-/proto}

mkdir -p "$OUT_DIR"
touch "$OUT_DIR/__init__.py"

python -m grpc_tools.protoc \
  --proto_path="$PROTO_DIR" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  "$PROTO_DIR/client_config.proto"

# protoc emits `import client_config_pb2` (top-level) in the _grpc stub. Rewrite
# to a relative import so the generated package works regardless of sys.path.
sed -i 's/^import client_config_pb2/from . import client_config_pb2/' \
  "$OUT_DIR/client_config_pb2_grpc.py"

echo "codegen: wrote _pb2 and _pb2_grpc into $OUT_DIR"
