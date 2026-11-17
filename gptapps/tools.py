"""Small strict argument validator for reviewed application function schemas."""
import math

KEYS={'type','description','properties','required','additionalProperties','items','enum',
      'minLength','maxLength','minimum','maximum','minItems','maxItems'}


def validate_schema(schema):
    if not isinstance(schema,dict) or set(schema)-KEYS:
        raise ValueError('Agents function schema uses unsupported validation keywords')
    kinds=schema.get('type');kinds=kinds if isinstance(kinds,list) else [kinds]
    if not kinds or any(k not in ('object','array','string','integer','number','boolean','null') for k in kinds):
        raise ValueError('Agents functions require explicit supported JSON types')
    if 'object' in kinds:
        if schema.get('additionalProperties') is not False:raise ValueError('Agents function objects require additionalProperties=false')
        props=schema.get('properties',{})
        if not isinstance(props,dict):raise ValueError('Invalid function properties')
        for child in props.values():validate_schema(child)
        if not isinstance(schema.get('required',[]),list) or any(k not in props for k in schema.get('required',[])):
            raise ValueError('Invalid required function properties')
    if 'array' in kinds:validate_schema(schema.get('items'))


def validate_arguments(value,schema):
    kinds=schema['type'];kinds=kinds if isinstance(kinds,list) else [kinds]
    valid={'object':isinstance(value,dict),'array':isinstance(value,list),'string':isinstance(value,str),
           'integer':type(value) is int,'number':type(value) in (int,float) and math.isfinite(value),
           'boolean':type(value) is bool,'null':value is None}
    if not any(valid[k] for k in kinds):raise ValueError('Tool argument type does not match its schema')
    if 'enum' in schema and value not in schema['enum']:raise ValueError('Tool argument is outside its enum')
    if isinstance(value,dict):
        props=schema.get('properties',{})
        if set(value)-set(props) or any(k not in value for k in schema.get('required',[])):
            raise ValueError('Tool arguments have missing or additional fields')
        for k,v in value.items():validate_arguments(v,props[k])
    elif isinstance(value,list):
        if not schema.get('minItems',0)<=len(value)<=schema.get('maxItems',10000):raise ValueError('Tool array length is invalid')
        for item in value:validate_arguments(item,schema['items'])
    elif isinstance(value,str):
        if not schema.get('minLength',0)<=len(value)<=schema.get('maxLength',100000):raise ValueError('Tool string length is invalid')
    elif type(value) in (int,float):
        if value<schema.get('minimum',-math.inf) or value>schema.get('maximum',math.inf):raise ValueError('Tool number is out of bounds')

