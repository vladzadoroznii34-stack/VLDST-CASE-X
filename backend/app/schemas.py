from pydantic import BaseModel,Field
class AuthRequest(BaseModel): init_data:str=Field(min_length=1,max_length=10000); referral_code:str|None=None
class OpenRequest(BaseModel): case_code:str; request_id:str=Field(min_length=8,max_length=100)
class SellRequest(BaseModel): item_code:str; quantity:int=Field(ge=1,le=10000)
class PinRequest(BaseModel): item_code:str; pinned:bool
class PaymentRequest(BaseModel): product_code:str
