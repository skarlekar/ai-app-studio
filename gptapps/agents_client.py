"""Thin optional official-SDK adapter. No SDK import or credential use for Responses."""
import os


def plain(value):
    return value.model_dump(mode='json') if hasattr(value,'model_dump') else value


def provider_error(error):
    status=getattr(error,'status_code',None)
    if status in (400,401,403,404,409,429,500,502,503,504):
        advice={401:'check the configured API key',403:'verify Agents and model access',
                429:'check quota, billing and rate limits',409:'reconcile the active session before retrying',
                400:'review the runtime and tool configuration'}
        return f'OpenAI Agents returned HTTP {status}; '+advice.get(status,'check session state before retrying')
    return 'OpenAI Agents connection failed; reconcile saved work before retrying'


class AgentsClient:
    def __init__(self,sdk=None):
        self._sdk=sdk

    @property
    def sdk(self):
        if self._sdk is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ValueError('Install optional Agents support: python -m pip install "openai==3.13.0"') from None
            if not os.environ.get('OPENAI_API_KEY'):
                raise ValueError('Set OPENAI_API_KEY in the server environment for Agents')
            # No automatic retries of session creation, and no environment-overridden origin.
            self._sdk=OpenAI(api_key=os.environ['OPENAI_API_KEY'],base_url='https://api.openai.com/v1',
                             max_retries=0,timeout=30)
        return self._sdk

    @property
    def sessions(self):
        try:
            return self.sdk.beta.agents.sessions
        except AttributeError:
            raise ValueError('Install optional Agents support with openai==3.13.0 or a verified compatible SDK') from None

    def create(self,agent,environment,message,run_id):
        # review is in the public API; SDK 3.13 exposes it via supported extra_body.
        return self.sessions.create(agent=agent,environment=environment,
            input=[{'role':'user','content':[{'type':'input_text','text':message}]}],
            metadata={'studio_run_id':run_id},extra_body={'review':'auto_review'},stream=True)

    def events(self,session_id):
        return self.sessions.events.stream(session_id,timeout=15)

    def send(self,session_id,message,submission_id):
        return self.sessions.events.create(session_id,idempotency_key=submission_id,
            events=[{'type':'agent.session.input.message','input':[
                {'role':'user','content':[{'type':'input_text','text':message}]}]}])

    def session(self,session_id):return plain(self.sessions.retrieve(session_id))
    def turns(self,session_id):return [plain(x) for x in self.sessions.turns.list(session_id,limit=100)]
    def turn(self,session_id,turn_id):return plain(self.sessions.turns.retrieve(turn_id,session_id=session_id))
    def items(self,session_id):return [plain(x) for x in self.sessions.items.list(session_id,order='asc',limit=100)]
    def artifacts(self,session_id):return [plain(x) for x in self.sessions.artifacts.list(session_id,limit=100)]

    def content(self,session_id,artifact_id):
        with self.sessions.artifacts.with_streaming_response.content(artifact_id,session_id=session_id) as response:
            yield from response.iter_bytes()

    def cancel(self,session_id):
        return self.sessions.events.create(session_id,events=[{'type':'agent.session.input.cancel'}])

    def tool_result(self,session_id,turn_id,call_id,result):
        return self.sessions.events.create(session_id,idempotency_key='tool-'+turn_id+'-'+call_id,
            events=[{'type':'agent.session.input.tool_result','turn_id':turn_id,'call_id':call_id,**result}])

    def upload(self,name,raw):
        return plain(self.sdk.files.create(file=(name,raw),purpose='user_data'))

    def attach(self,environment_id,path,file_id):
        return plain(self.sdk.beta.agents.environments.files.create(environment_id,path=path,type='file_id',file_id=file_id))

    def search(self,store_id,query):
        return plain(self.sdk.vector_stores.search(store_id,query=query,max_num_results=8))

    def inventory(self,store_id):
        files=[]
        for item in self.sdk.vector_stores.files.list(store_id,limit=100):
            files.append(plain(item))
            if len(files)>1000:raise ValueError("Knowledge collection inventory exceeds the supported limit")
        return files

    def collection(self,store_id):
        return plain(self.sdk.vector_stores.retrieve(store_id))

    def delete(self,session_id):return self.sessions.delete(session_id)
    def delete_file(self,file_id):return self.sdk.files.delete(file_id)


def sdk_available():
    try:
        from openai.resources.beta.agents import Agents
        return hasattr(Agents,'sessions')
    except ImportError:
        return False
