import streamlit as st

from core import lims_db
from core.store import load_papers

st.set_page_config(page_title="Research Lab", page_icon="🧪", layout="wide")
lims_db.init_db()

STATUS_COLORS = {"계획": "gray", "진행중": "blue", "완료": "green", "보류": "orange"}

st.title("Research Lab", icon=":material/science:")
st.caption("연구실 미니 LIMS — 프로젝트 → 샘플 → 실험 → 결과")

# ---------- 대시보드 KPI ----------
counts = lims_db.dashboard_counts()
reports = sum(1 for p in load_papers() if p.get("protocol"))

with st.container(horizontal=True):
    st.metric("Projects", counts["projects"], border=True)
    st.metric("Samples", counts["samples"], border=True)
    st.metric("Experiments", counts["experiments"], border=True)
    st.metric("Reports", reports, border=True, help="논문 프로토콜 AI에서 생성된 프로토콜 수")

# ---------- 새 프로젝트 ----------
with st.expander("새 프로젝트 추가", icon=":material/add:"):
    with st.form("new_project_form", clear_on_submit=True):
        name = st.text_input("프로젝트 이름")
        description = st.text_area("설명", height=80)
        submitted = st.form_submit_button("추가")
        if submitted:
            if not name.strip():
                st.error("프로젝트 이름을 입력해주세요.")
            else:
                lims_db.create_project(name.strip(), description.strip())
                st.success(f"'{name}' 프로젝트를 추가했습니다.", icon=":material/check_circle:")
                st.rerun()

# ---------- 프로젝트 목록 (카드) ----------
st.subheader("프로젝트", icon=":material/folder:")
search = st.text_input("프로젝트 검색", placeholder="이름 또는 설명으로 검색", label_visibility="collapsed")
projects = lims_db.list_projects(search=search)

if not projects:
    st.caption("아직 프로젝트가 없습니다. 위에서 새 프로젝트를 추가해보세요.")

for proj in projects:
    with st.container(border=True):
        title_row = st.container(horizontal=True, vertical_alignment="center")
        title_row.markdown(f"#### {proj['name']}")
        title_row.badge(f"샘플 {proj['sample_count']}", color="blue")
        title_row.badge(f"실험 {proj['experiment_count']}", color="violet")

        if proj["description"]:
            st.caption(proj["description"])

        samples = sorted(lims_db.list_samples(project_id=proj["id"]), key=lambda s: s["code"])
        if not samples:
            st.caption("샘플이 아직 없습니다.")
        else:
            for s in samples:
                exps = sorted(lims_db.list_experiments(sample_id=s["id"]), key=lambda e: e["exp_type"])
                row = st.container(horizontal=True, vertical_alignment="center")
                row.markdown(f"🧪 **{s['code']}**")
                if not exps:
                    row.caption("실험 없음")
                else:
                    for e in exps:
                        row.badge(e["exp_type"], color=STATUS_COLORS.get(e["status"], "gray"))

        if st.button("LIMS에서 열기", key=f"open_{proj['id']}", icon=":material/open_in_new:"):
            st.session_state["lims_project_id"] = proj["id"]
            st.switch_page("pages/2_🧪_LIMS.py")
