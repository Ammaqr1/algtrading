from grpc_tools import protoc
import upstox_client
from upstox_client.rest import ApiException
# import websocket_for_us_data
# protoc.main((
#     '',
#     r'-IC:\Users\ammar\Downloads',     # proto files location
#     '--python_out=.',                  # generate to working dir
#     r'C:\Users\ammar\Downloads\MarketDataFeed.proto',    # compile this file with full path
# ))

from upstox_client.models.gtt_order_details import GttOrderDetails  # noqa: E501

model = upstox_client.models.gtt_order_details.GttOrderDetails(gtt_order_id='GTT-C25071000233916')
print(model.to_dict())
