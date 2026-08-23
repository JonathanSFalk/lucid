import anvil.secrets
import anvil.server
import grpc
import grpc.aio
import asyncio

@anvil.server.callable
def test_grpc_import():
  return {"grpc_version": grpc.__version__}
async def _grpc_channel_test():
    channel = grpc.aio.secure_channel("mobile.deneb.prod.infotainment.pdx.atieva.com:443", grpc.ssl_channel_credentials())
    try:
      await asyncio.wait_for(channel.channel_ready(), timeout=10)
      result = "SUCCESS: channel became ready"
    except Exception as e:
      result = "FAILED: " + type(e).__name__ + ": " + str(e)
    await channel.close()
    return result

@anvil.server.callable
def test_grpc_connection():
  return asyncio.run(_grpc_channel_test())
      