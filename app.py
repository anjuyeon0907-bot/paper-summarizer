import io
import os

import arxiv
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

load_dotenv()

st.set_page_config(page_title="논문 요약 도우미", page_icon=":material/science:")

NAMING_NOTE = (
    "학명, 화합물명, 시약명, 세포주명, 유전자명 등 고유명사는 임의로 번역하거나 다른 명칭으로 "
    "바꾸지 말고 논문에 쓰인 원문 표기를 그대로 사용하세요. 한국어 통용명이 논문에 없다면 "
    "지어내지 말고 원문(학명 등)을 그대로 쓰세요."
)

SUMMARY_PROMPT = f"""당신은 연구를 돕는 전문 분석가입니다. 아래 논문 내용을 분석하여 다음 5가지 항목을 Markdown 형식으로 한국어로 작성해주세요.
각 항목의 제목은 아래 형식을 그대로 사용하세요. {NAMING_NOTE}

## 🎯 핵심 요약 (3줄)

## 💡 주요 기여점 (Main Contribution)

## 🧪 제안하는 방법론 및 핵심 알고리즘

## ⚠️ 연구의 한계점 (Limitations)

## 🔍 내 연구에의 적용 포인트

---
논문 제목: {{title}}

논문 내용:
{{paper_text}}
"""

PROTOCOL_PROMPT = f"""당신은 실험 프로토콜을 정리하는 전문 연구보조원입니다. 아래 논문에서 Materials and Methods(재료 및 방법) 부분을 찾아,
다른 연구자가 실험을 그대로 재현할 수 있도록 Markdown으로 정리해주세요. {NAMING_NOTE}
논문에 명시되지 않은 내용은 추측해서 채우지 말고 "명시되지 않음"이라고 쓰세요.

## 🧫 재료 (시료·시약·세포주·장비)

## 🔬 실험 절차 (단계별)

## ⚙️ 주요 파라미터 (농도·온도·시간·배율 등)

## 📊 통계 분석 방법

---
논문 제목: {{title}}

논문 내용:
{{paper_text}}
"""

# Keep well under typical context limits regardless of model choice.
MAX_INPUT_CHARS = 15000

# Gemini exposes an OpenAI-compatible endpoint, so the openai client works as-is.
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


@st.cache_data(ttl="1h", max_entries=50)
def search_arxiv(query: str, max_results: int = 5) -> list[dict]:
    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )
    results = []
    for r in client.results(search):
        results.append(
            {
                "title": r.title,
                "authors": ", ".join(a.name for a in r.authors),
                "summary": r.summary,
                "url": r.entry_id,
                "published": r.published.strftime("%Y-%m-%d") if r.published else "",
            }
        )
    return results


def extract_pdf_text(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def run_llm(client: OpenAI, model: str, prompt_template: str, title: str, paper_text: str) -> str:
    prompt = prompt_template.format(title=title, paper_text=paper_text[:MAX_INPUT_CHARS])
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content


with st.sidebar:
    st.header("설정")
    api_key = st.text_input(
        "Gemini API 키",
        type="password",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="입력한 키는 저장되지 않고 이 세션에서만 사용됩니다. Google AI Studio에서 발급받은 키를 입력하세요.",
    )
    model = st.text_input(
        "모델",
        value="gemini-3.6-flash",
        help="Gemini 모델명은 자주 바뀝니다. 오류가 나면 https://ai.google.dev/gemini-api/docs/models 에서 현재 사용 가능한 모델명을 확인해 입력하세요.",
    )

st.title("논문 요약 도우미")
st.caption("arXiv 검색 또는 PDF 업로드로 논문을 분석하고 연구에 필요한 항목을 추출합니다.")

tab_search, tab_pdf, tab_protocol = st.tabs(
    [
        ":material/search: arXiv 검색",
        ":material/upload_file: PDF 업로드",
        ":material/biotech: 프로토콜 추출",
    ]
)

with tab_search:
    query = st.text_input("검색 키워드", placeholder="예: diffusion model")
    if st.button("검색", icon=":material/search:") and query:
        with st.spinner("arXiv에서 논문을 검색하는 중..."):
            st.session_state["arxiv_results"] = search_arxiv(query)

    for i, paper in enumerate(st.session_state.get("arxiv_results", [])):
        with st.container(border=True):
            st.markdown(f"**{paper['title']}**")
            st.caption(f"{paper['authors']} · {paper['published']}")
            with st.expander("초록 보기"):
                st.write(paper["summary"])

            if st.button("요약하기", key=f"summarize_arxiv_{i}", icon=":material/auto_awesome:"):
                if not api_key:
                    st.warning("사이드바에 API 키를 입력해주세요.")
                else:
                    with st.spinner("LLM으로 분석하는 중..."):
                        try:
                            client = OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL)
                            st.session_state[f"summary_arxiv_{i}"] = run_llm(
                                client, model, SUMMARY_PROMPT, paper["title"], paper["summary"]
                            )
                        except Exception as e:
                            st.error(f"요약 중 오류가 발생했습니다: {e}")

            summary = st.session_state.get(f"summary_arxiv_{i}")
            if summary:
                st.markdown(summary)
                st.download_button(
                    "마크다운 다운로드",
                    data=summary,
                    file_name=f"{paper['title'][:50]}_summary.md",
                    mime="text/markdown",
                    icon=":material/download:",
                    key=f"download_arxiv_{i}",
                )

with tab_pdf:
    uploaded_file = st.file_uploader(
        "논문 PDF 업로드", type=["pdf"], key="pdf_uploader_summary"
    )

    if uploaded_file and st.button(
        "요약하기", key="summarize_pdf", icon=":material/auto_awesome:"
    ):
        if not api_key:
            st.warning("사이드바에 API 키를 입력해주세요.")
        else:
            with st.spinner("PDF에서 텍스트를 추출하는 중..."):
                pdf_text = extract_pdf_text(uploaded_file.read())
            with st.spinner("LLM으로 분석하는 중..."):
                try:
                    client = OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL)
                    st.session_state["summary_pdf"] = run_llm(
                        client, model, SUMMARY_PROMPT, uploaded_file.name, pdf_text
                    )
                except Exception as e:
                    st.error(f"요약 중 오류가 발생했습니다: {e}")

    pdf_summary = st.session_state.get("summary_pdf")
    if pdf_summary:
        st.markdown(pdf_summary)
        st.download_button(
            "마크다운 다운로드",
            data=pdf_summary,
            file_name="pdf_summary.md",
            mime="text/markdown",
            icon=":material/download:",
            key="download_pdf",
        )

with tab_protocol:
    st.caption("논문의 Materials and Methods를 바탕으로 재현 가능한 실험 프로토콜을 추출합니다.")
    protocol_file = st.file_uploader(
        "논문 PDF 업로드", type=["pdf"], key="pdf_uploader_protocol"
    )

    if protocol_file and st.button(
        "프로토콜 추출하기", key="extract_protocol", icon=":material/biotech:"
    ):
        if not api_key:
            st.warning("사이드바에 API 키를 입력해주세요.")
        else:
            with st.spinner("PDF에서 텍스트를 추출하는 중..."):
                protocol_text = extract_pdf_text(protocol_file.read())
            with st.spinner("LLM으로 프로토콜을 정리하는 중..."):
                try:
                    client = OpenAI(api_key=api_key, base_url=GEMINI_BASE_URL)
                    st.session_state["protocol_result"] = run_llm(
                        client, model, PROTOCOL_PROMPT, protocol_file.name, protocol_text
                    )
                except Exception as e:
                    st.error(f"프로토콜 추출 중 오류가 발생했습니다: {e}")

    protocol_result = st.session_state.get("protocol_result")
    if protocol_result:
        st.markdown(protocol_result)
        st.download_button(
            "마크다운 다운로드",
            data=protocol_result,
            file_name="protocol.md",
            mime="text/markdown",
            icon=":material/download:",
            key="download_protocol",
        )

