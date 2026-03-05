from core.llm import OnPremiseLLM
from core.retriever import LogisticsRetriever
from langchain_core.prompts import ChatPromptTemplate
from prompts.rag_prompts import RAG_PROMPT_TEMPLATE

class QueryProcessor:
    def __init__(self):
        self.llm = OnPremiseLLM()
        self.retriever = LogisticsRetriever()
        self.prompt = ChatPromptTemplate.from_template(RAG_PROMPT_TEMPLATE)

    def get_response(self, query: str, chat_history: list = []):
        docs = self.retriever.search(query)
        context_list = []
        for d in docs:
            # 'content' 키가 없을 경우를 대비해 빈 문자열이나 다른 키 확인
            content = d.payload.get('content') or d.payload.get('page_content') or ""
            context_list.append(content)
            
        context = "\n".join(context_list)
        
        # 프롬프트 실행
        chain = self.prompt | self.llm
        answer = chain.invoke({
            "context": context, 
            "question": query, 
            "chat_history": chat_history
        })
        
        # sources 추출 시에도 안전하게 get() 사용
        sources = [d.payload.get('metadata', {}).get('source', 'Unknown') for d in docs]
        
        return {"answer": answer, "sources": list(set(sources))}