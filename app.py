import os
import re
import streamlit as st
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# ==========================================
# 1. 페이지 설정 및 연두색 테마 CSS
# ==========================================
st.set_page_config(
    page_title="뭐 먹을지 고민하지마!",
    page_icon="🥦",
    layout="wide",
)

st.markdown("""
<style>
    .stApp { background-color: #f8fbf6; }
    h1, h2, h3 { color: #2e7d32 !important; }
    .stButton > button[kind="primary"] {
        background-color: #4caf50 !important;
        border-color: #4caf50 !important;
        color: white !important;
        font-weight: bold !important;
        border-radius: 10px !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #2e7d32 !important;
        border-color: #2e7d32 !important;
    }
    .cal-header {
        text-align: center;
        font-weight: bold;
        background: #e8f5e9;
        color: #1b5e20;
        padding: 8px 4px;
        border-radius: 6px;
        margin-bottom: 6px;
    }
    .cal-meal-label {
        text-align: center;
        font-weight: bold;
        background: #f9fbe7;
        color: #33691e;
        padding: 10px 4px;
        border-radius: 6px;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. Gemini API 클라이언트 초기화 (Streamlit Secrets 사용)
# ==========================================
api_key = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY"))
if not api_key:
    st.error("⚠️ GEMINI_API_KEY가 설정되지 않았습니다. Streamlit Cloud의 Settings → Secrets에 API 키를 등록해 주세요.")
    st.stop()

client = genai.Client(api_key=api_key)

# ==========================================
# 3. Pydantic 스키마 정의
# ==========================================
class Nutrition(BaseModel):
    calories: int = Field(description="예상 열량 (kcal)")
    calories_comparison: str = Field(description="열량 체감 비교 (예: 밥 한 공기(300kcal)의 1.5배)")
    carbs_pct: int = Field(description="탄수화물 비율 (%) - 정수형")
    protein_pct: int = Field(description="단백질 비율 (%) - 정수형")
    fat_pct: int = Field(description="지방 비율 (%) - 정수형")
    other_nutrients: str = Field(description="철분, 비타민, 나트륨 등 기타 영양소 정보를 g 또는 mg 단위와 함께 서술")

class Dish(BaseModel):
    name: str = Field(description="요리 이름")
    ingredients_summary: str = Field(description="주요 재료 조합 요약")
    recipe_steps: list[str] = Field(
        description="텍스트 길이 제한 없이, 불 조절과 시간, 재료 상태 변화를 모두 포함하여 상세하게 작성된 단계별 레시피 리스트 (각 항목 앞에 '1.', '2.' 같은 번호를 절대 붙이지 말 것)"
    )
    nutrition: Nutrition
    food_waste_guide: str = Field(description="주의해야 할 쓰레기의 배출 위치. 이유는 생략하고 '계란껍질 - 일반쓰레기' 형태로 단순하게 작성")

class RecipeRecommendations(BaseModel):
    dishes: list[Dish] = Field(min_length=5, max_length=5, description="정확히 5개의 요리 추천")

class ShoppingItem(BaseModel):
    name: str = Field(description="식재료 이름")
    amount: str = Field(description="한 주 동안 필요한 양")
    estimated_price: int = Field(description="예상 구매 가격 (원 단위 정수)")

class DailyPlan(BaseModel):
    day: str = Field(description="요일 (월, 화, 수, 목, 금, 토, 일)")
    breakfast: str = Field(description="아침 메뉴 (선택하지 않은 끼니라면 반드시 '-' 입력)")
    lunch: str = Field(description="점심 메뉴 (선택하지 않은 끼니라면 반드시 '-' 입력)")
    dinner: str = Field(description="저녁 메뉴 (선택하지 않은 끼니라면 반드시 '-' 입력)")

class WeeklyMealPlan(BaseModel):
    shopping_list: list[ShoppingItem] = Field(description="장보기 리스트")
    daily_plans: list[DailyPlan] = Field(min_length=7, max_length=7, description="월~일 7일간 식단")
    total_estimated_cost: int = Field(description="총 예상 금액 합계")
    tip: str = Field(description="자취생 살림 팁")

# ==========================================
# 4. 공통 상수 및 세션 상태 초기화
# ==========================================
QUICK_ING_CHOICES = ["계란", "대파", "양파", "마늘", "간장", "설탕", "소금", "참기름", "김치", "스팸"]
GENRE_CHOICES = ["한식", "양식", "중식", "일식", "분식", "동남아/아시안", "건강식/다이어트", "퓨전"]
FOOD_TYPE_CHOICES = ["밥", "면", "빵", "고기/메인요리", "샐러드/가벼운 식사", "상관없음"]
SOUP_STYLE_CHOICES = ["국물요리 (국/탕/찌개)", "볶음/구이요리", "찜/조림요리", "튀김/전", "비빔/무침", "상관없음"]
DAYS = ["월", "화", "수", "목", "금", "토", "일"]
MEAL_CHOICES = ["아침", "점심", "저녁"]

SPICINESS_DESC = {
    0: "0단계 (전혀 안 매움 - 백숙, 크림파스타, 간장 계란밥 수준)",
    1: "1단계 (살짝 매콤함 - 진라면 순한맛, 진미채 볶음 수준)",
    2: "2단계 (적당히 매콤함 - 신라면, 김치찌개 수준)",
    3: "3단계 (꽤 매움 - 열라면, 매운 떡볶이 수준)",
    4: "4단계 (아주 매움 - 불닭볶음면, 엽기떡볶이 오리지널 수준)",
    5: "5단계 (극한의 매운맛 - 핵불닭볶음면, 엽기떡볶이 매운맛 수준)"
}

def init_state():
    defaults = {
        "page": "home",
        "quick_picks": [],
        "opt_ing_text": "",
        "p2_genres": ["한식", "양식"],
        "p2_types": ["밥", "면"],
        "p2_styles": ["국물요리 (국/탕/찌개)", "볶음/구이요리"],
        "res_1": None,
        "res_2": None,
        "meal_plan": None,
        "meal_budget": 50000,
        "meal_goal": "일반식 (균형 잡힌 집밥)",
        "meal_schedule": {d: ["점심", "저녁"] for d in DAYS},
        "selected_menu": None,
        "detail_dish": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    for d in DAYS:
        if f"day_{d}" not in st.session_state:
            st.session_state[f"day_{d}"] = ["점심", "저녁"]

init_state()

def go_page(page_name):
    st.session_state.page = page_name

# 전체 선택/해제 콜백 함수
def toggle_list_state(key, all_choices):
    if len(st.session_state[key]) == len(all_choices):
        st.session_state[key] = []
    else:
        st.session_state[key] = list(all_choices)

def toggle_quick_all():
    current_list = [x.strip() for x in st.session_state.opt_ing_text.split(",") if x.strip()]
    if len(st.session_state.quick_picks) == len(QUICK_ING_CHOICES):
        st.session_state.quick_picks = []
        st.session_state.opt_ing_text = ", ".join([x for x in current_list if x not in QUICK_ING_CHOICES])
    else:
        st.session_state.quick_picks = list(QUICK_ING_CHOICES)
        for item in QUICK_ING_CHOICES:
            if item not in current_list:
                current_list.append(item)
        st.session_state.opt_ing_text = ", ".join(current_list)

def sync_quick_to_text():
    current_list = [x.strip() for x in st.session_state.opt_ing_text.split(",") if x.strip()]
    for item in st.session_state.quick_picks:
        if item not in current_list:
            current_list.append(item)
    st.session_state.opt_ing_text = ", ".join(current_list)

def toggle_all_days():
    all_checked = all(len(st.session_state[f"day_{d}"]) == len(MEAL_CHOICES) for d in DAYS)
    new_val = [] if all_checked else list(MEAL_CHOICES)
    for d in DAYS:
        st.session_state[f"day_{d}"] = list(new_val)

# ==========================================
# 5. HTML 렌더링 및 API 호출 함수
# ==========================================
def render_dish_card(dish: Dish, index: int = None, open_by_default: bool = False):
    cleaned_steps = [re.sub(r'^\s*\d+[\.\)]\s*', '', step).strip() for step in dish.recipe_steps]
    recipe_html = "<br><br>".join([f"<b>{idx+1}.</b> {step}" for idx, step in enumerate(cleaned_steps)])

    carbs_end = dish.nutrition.carbs_pct
    protein_end = carbs_end + dish.nutrition.protein_pct
    prefix = f"{index}. " if index is not None else ""

    with st.expander(f"🍽️ {prefix}{dish.name}  (재료 조합: {dish.ingredients_summary})", expanded=open_by_default):
        st.markdown(f"""
        <div style="line-height: 1.7; color: #333;">
            <h4 style="margin-bottom: 8px; color: #2e7d32;">📖 단계별 상세 레시피</h4>
            <div style="background: white; padding: 15px; border-radius: 8px; border-left: 4px solid #aed581; margin-bottom: 16px;">
                {recipe_html}
            </div>
            <h4 style="margin-bottom: 8px; color: #2e7d32;">💪 건강 정보 및 탄단지 비율</h4>
            <div style="background: white; padding: 15px; border-radius: 8px; border-left: 4px solid #4db6ac; margin-bottom: 16px;">
                <div style="display: flex; align-items: center; gap: 25px; flex-wrap: wrap;">
                    <div style="width: 96px; height: 96px; border-radius: 50%; flex-shrink: 0;
                                background: conic-gradient(
                                    #ef5350 0% {carbs_end}%,
                                    #42a5f5 {carbs_end}% {protein_end}%,
                                    #ffd54f {protein_end}% 100%
                                ); box-shadow: 0 3px 6px rgba(0,0,0,0.1);">
                    </div>
                    <div>
                        <div style="font-weight: bold; font-size: 1.1em;">🔥 열량: {dish.nutrition.calories} kcal</div>
                        <div style="font-size: 0.9em; color: gray; margin-bottom: 8px;">({dish.nutrition.calories_comparison})</div>
                        <div>🔴 탄수화물 {dish.nutrition.carbs_pct}% &nbsp;&nbsp; 🔵 단백질 {dish.nutrition.protein_pct}% &nbsp;&nbsp; 🟡 지방 {dish.nutrition.fat_pct}%</div>
                    </div>
                </div>
                <div style="margin-top: 12px; padding-top: 10px; border-top: 1px dashed #ccc; font-size: 0.95em;">
                    🌱 <b>기타 영양소:</b> {dish.nutrition.other_nutrients}
                </div>
            </div>
            <h4 style="margin-bottom: 8px; color: #2e7d32;">♻️ 쓰레기 처리 가이드</h4>
            <div style="background: white; padding: 12px 15px; border-radius: 8px; border-left: 4px solid #81c784;">
                {dish.food_waste_guide}
            </div>
        </div>
        """, unsafe_allow_html=True)

def call_gemini_recipes(prompt: str):
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction="당신은 창의적이고 전문적인 셰프입니다. 사용자의 요리 실력에 맞춰 레시피를 작성하되, 중급과 숙련은 아주 상세하고 친절하게 설명해야 합니다. 한식, 양식, 일식, 퓨전 등 다양한 장르를 포함하세요. 쓰레기 처리법은 이유 없이 배출처만 직관적으로 작성하세요.",
            response_mime_type="application/json",
            response_schema=RecipeRecommendations,
        ),
    )
    return response.parsed or RecipeRecommendations.model_validate_json(response.text)

# ==========================================
# 6. 공통 헤더
# ==========================================
st.markdown("""
<div style="text-align: center; padding: 10px 0 20px 0;">
    <h1 style="color: #558b2f; margin-bottom: 5px;">🥦 뭐 먹을지 고민하지마!</h1>
    <p style="font-size: 16px; color: #555;">요리 실력에 맞춘 초상세 레시피부터 자취생 일주일 식단표까지 한 번에!</p>
</div>
""", unsafe_allow_html=True)

# ==========================================
# [화면 0] 메인 홈 화면
# ==========================================
if st.session_state.page == "home":
    st.markdown("<h3 style='text-align: center; color: #444; margin-top: 20px;'>원하시는 메뉴를 선택해 주세요 👇</h3>", unsafe_allow_html=True)
    st.write("")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.button("🧊 1. 냉장고 터는 날~", type="primary", use_container_width=True, on_click=go_page, args=("page_1",))
    with c2:
        st.button("🤔 2. 오늘 뭐먹지?", type="primary", use_container_width=True, on_click=go_page, args=("page_2",))
    with c3:
        st.button("📅 3. 자취생 이 주의 식단 짜주기", type="primary", use_container_width=True, on_click=go_page, args=("page_3",))

# ==========================================
# [화면 1] 냉장고 터는 날~
# ==========================================
elif st.session_state.page == "page_1":
    st.button("🏠 처음 화면으로 돌아가기", on_click=go_page, args=("home",))
    st.subheader("🧊 냉장고 터는 날~")

    skill_1 = st.radio("🔥 나의 요리 실력 선택", ["초급", "중급", "숙련"], horizontal=True)
    st.caption("* 중급/숙련 선택 시 따라만 하면 되는 아주 상세한 레시피가 제공됩니다.")

    col_left, col_right = st.columns([1, 1.3], gap="large")
    with col_left:
        req_ing = st.text_area("🚨 필수 사용 재료 (꼭 소진해야 하는 재료)", placeholder="예: 유통기한 임박한 두부, 남은 삼겹살, 애호박", height=80)

        st.button("☑️ 자주 쓰는 부가 재료 전체 선택 / 해제", on_click=toggle_quick_all)
        st.multiselect("⚡ 자주 쓰는 부가 재료 빠르게 추가하기", QUICK_ING_CHOICES, key="quick_picks", on_change=sync_quick_to_text)

        opt_ing = st.text_area("🥬 부가 재료 (있으면 활용하는 재료)", key="opt_ing_text", placeholder="예: 계란, 대파, 양파, 간장, 버터...", height=80)
        tools = st.text_area("🍳 보유 조리 기구", value="가스레인지, 프라이팬, 냄비, 도마, 칼", height=70)

        if st.button("✨ 냉장고 털기 레시피 5개 추천받기", type="primary", use_container_width=True):
            if not req_ing.strip():
                st.warning("⚠️ 냉장고에서 꼭 소진해야 할 '필수 사용 재료'를 입력해 주세요.")
            elif not tools.strip():
                st.warning("⚠️ 보유 조리 기구를 입력해 주세요.")
            else:
                opt_text = opt_ing.strip() if opt_ing.strip() else "없음 (기본 양념만 최소한으로 활용)"
                skill_inst = ""
                if skill_1 in ["중급", "숙련"]:
                    skill_inst = "\n[매우 중요] 선택된 난이도가 중급 이상입니다. 텍스트 길이 제한을 두지 말고, 재료 손질법부터 불의 세기, 조리 시간(분/초), 재료 상태 변화까지 아주 구체적이고 길게 단계별로 작성하세요."
                if skill_1 == "숙련":
                    skill_inst += "\n[추가 중요] 5가지 요리 중 최소 1가지는 파인다이닝 레스토랑 수준의 고급 퓨전 코스 메인 디쉬 형태로 포함하세요."

                prompt = f"""
                [필수 사용 재료 (모든 요리에 반드시 포함)]: {req_ing}
                [부가 재료]: {opt_text}
                [보유 조리 기구]: {tools}
                [요리 실력]: {skill_1}
                냉장고를 털기 위한 요리 5가지를 추천해 주세요. 한식, 양식, 일식, 퓨전 등 장르를 다양하게 구성하세요.
                {skill_inst}
                """
                with st.spinner(f"👨‍🍳 [{skill_1}] 냉장고 털기 맞춤 레시피 5가지를 작성하고 있습니다... (약 10~15초 소요)"):
                    try:
                        st.session_state.res_1 = (skill_1, call_gemini_recipes(prompt))
                    except Exception as e:
                        st.error(f"❌ 오류가 발생했습니다: {e}")

    with col_right:
        if st.session_state.res_1:
            saved_skill, result = st.session_state.res_1
            st.markdown(f"### 👨‍🍳 [{saved_skill}] 맞춤 레시피 TOP 5")
            for i, dish in enumerate(result.dishes, 1):
                render_dish_card(dish, index=i)

# ==========================================
# [화면 2] 오늘 뭐먹지?
# ==========================================
elif st.session_state.page == "page_2":
    st.button("🏠 처음 화면으로 돌아가기", on_click=go_page, args=("home",))
    st.subheader("🤔 오늘 뭐먹지?")

    skill_2 = st.radio("🔥 나의 요리 실력 선택", ["초급", "중급", "숙련"], index=1, horizontal=True)
    st.caption("* 중급/숙련 선택 시 따라만 하면 되는 아주 상세한 레시피가 제공됩니다.")

    col_left, col_right = st.columns([1, 1.3], gap="large")
    with col_left:
        st.button("☑️ 음식 분야 전체 선택 / 해제", on_click=toggle_list_state, args=("p2_genres", GENRE_CHOICES))
        genres = st.multiselect("선택 1. 음식 분야 (중복 선택 가능)", GENRE_CHOICES, key="p2_genres")

        st.button("☑️ 음식 종류 전체 선택 / 해제", on_click=toggle_list_state, args=("p2_types", FOOD_TYPE_CHOICES))
        food_types = st.multiselect("선택 2. 음식의 종류 (중복 선택 가능)", FOOD_TYPE_CHOICES, key="p2_types")

        st.button("☑️ 국물 및 조리 형태 전체 선택 / 해제", on_click=toggle_list_state, args=("p2_styles", SOUP_STYLE_CHOICES))
        soup_styles = st.multiselect("선택 3. 국물의 여부 및 조리 형태 (중복 선택 가능)", SOUP_STYLE_CHOICES, key="p2_styles")

        spiciness = st.slider("선택 4. 음식의 맵기 (0~5단계)", 0, 5, 2)
        with st.expander("🌶️ 맵기 단계별 설명 보기 (클릭해서 확인)"):
            st.markdown("""
            - **0단계:** 전혀 안 매움 *(백숙, 크림 파스타, 간장 계란밥)*
            - **1단계:** 살짝 매콤함 *(진라면 순한맛, 진미채 볶음)*
            - **2단계:** 적당히 매콤함 *(신라면, 일반적인 김치찌개)*
            - **3단계:** 꽤 매움 *(열라면, 매콤한 떡볶이, 제육볶음)*
            - **4단계:** 아주 매움 *(불닭볶음면, 엽기떡볶이 오리지널)*
            - **5단계:** 극한의 매운맛 *(핵불닭볶음면, 엽기떡볶이 매운맛)*
            """)

        if st.button("✨ 맞춤 메뉴 5개 추천받기", type="primary", use_container_width=True):
            if not genres or not food_types or not soup_styles:
                st.warning("⚠️ 음식 분야, 종류, 국물 여부를 각각 1개 이상 선택해 주세요.")
            else:
                skill_inst = ""
                if skill_2 in ["중급", "숙련"]:
                    skill_inst = "\n[매우 중요] 텍스트 길이 제한을 두지 말고, 재료 손질법, 불 세기, 조리 시간, 재료 상태 변화까지 아주 구체적이고 길게 단계별로 작성하세요."
                if skill_2 == "숙련":
                    skill_inst += "\n[추가 중요] 5가지 중 최소 1가지는 파인다이닝 레스토랑 수준의 고급 요리로 포함하세요."

                prompt = f"""
                [선택 1. 음식 분야]: {', '.join(genres)}
                [선택 2. 음식의 종류]: {', '.join(food_types)}
                [선택 3. 국물 및 조리 형태]: {', '.join(soup_styles)}
                [선택 4. 음식의 맵기]: {SPICINESS_DESC[spiciness]}
                [요리 실력]: {skill_2}
                위 4가지 조건에 딱 맞는 메뉴 5가지를 선별해 주세요.
                {skill_inst}
                """
                with st.spinner(f"👨‍🍳 [{skill_2}] 오늘의 맞춤 메뉴 5가지를 고르고 있습니다... (약 10~15초 소요)"):
                    try:
                        st.session_state.res_2 = (skill_2, call_gemini_recipes(prompt))
                    except Exception as e:
                        st.error(f"❌ 오류가 발생했습니다: {e}")

    with col_right:
        if st.session_state.res_2:
            saved_skill, result = st.session_state.res_2
            st.markdown(f"### 👨‍🍳 [{saved_skill}] 맞춤 레시피 TOP 5")
            for i, dish in enumerate(result.dishes, 1):
                render_dish_card(dish, index=i)

# ==========================================
# [화면 3] 자취생 이 주의 식단 짜주기
# ==========================================
elif st.session_state.page == "page_3":
    st.button("🏠 처음 화면으로 돌아가기", on_click=go_page, args=("home",))
    st.subheader("📅 자취생을 위한 이 주의 식단 짜주기")

    with st.container(border=True):
        budget = st.number_input("💰 한 주 식비 예산 (원, 직접 입력)", min_value=5000, value=50000, step=1000)

        h_col1, h_col2 = st.columns([3, 1])
        with h_col1:
            st.markdown("**🍽️ 요일별 챙겨 먹는 끼니 선택** *(안 먹는 끼니는 체크 해제하세요)*")
        with h_col2:
            st.button("☑️ 모든 요일 전체 선택 / 해제", on_click=toggle_all_days, use_container_width=True)

        day_cols = st.columns(7)
        for idx, d in enumerate(DAYS):
            with day_cols[idx]:
                st.multiselect(f"{d}요일", MEAL_CHOICES, key=f"day_{d}")

        goal = st.radio(
            "🎯 식단 목적 선택",
            ["일반식 (균형 잡힌 집밥)", "다이어트 (저칼로리/체중감량)", "고단백/벌크업 (운동 식단)", "초절약/가성비 (극강의 식비 절약)"],
            horizontal=True
        )

        if st.button("✨ 이 주의 식단표 & 장보기 리스트 만들기", type="primary", use_container_width=True):
            schedule = {d: st.session_state[f"day_{d}"] for d in DAYS}
            all_selected = set(m for meals in schedule.values() for m in meals)
            if not all_selected:
                st.warning("⚠️ 최소 1개 이상의 요일에서 끼니를 선택해 주세요.")
            else:
                schedule_lines = [
                    f"- {d}요일: {', '.join(schedule[d]) if schedule[d] else '식사 없음 (모두 - 표기)'}"
                    for d in DAYS
                ]
                prompt = f"""
                [한 주 식비 예산]: {int(budget):,}원
                [식단 목적]: {goal}
                [요일별 챙겨 먹는 끼니]:
                {chr(10).join(schedule_lines)}
                대한민국 자취생의 현실적인 마트 평균 물가를 반영해 1주일 식단표와 장보기 리스트를 짜주세요.
                선택되지 않은 요일/끼니는 반드시 '-'로 표기하고, 장보기 총합이 예산({int(budget):,}원) 이내로 맞도록 구성하세요.
                """
                with st.spinner(f"👨‍🍳 예산 {int(budget):,}원 / [{goal}] 일주일 식단표를 짜고 있습니다... (약 10~15초 소요)"):
                    try:
                        res = client.models.generate_content(
                            model="gemini-3.1-flash-lite",
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                system_instruction="당신은 자취생 전문 영양사 겸 살림 고수입니다. 한국어로 제공하세요.",
                                response_mime_type="application/json",
                                response_schema=WeeklyMealPlan,
                            ),
                        )
                        st.session_state.meal_plan = res.parsed or WeeklyMealPlan.model_validate_json(res.text)
                        st.session_state.meal_budget = int(budget)
                        st.session_state.meal_goal = goal
                        st.session_state.meal_schedule = schedule
                    except Exception as e:
                        st.error(f"❌ 오류가 발생했습니다: {e}")

    # 결과 출력 (장보기 리스트 + 클릭형 캘린더)
    if st.session_state.meal_plan:
        plan = st.session_state.meal_plan
        saved_budget = st.session_state.meal_budget
        saved_goal = st.session_state.meal_goal
        saved_schedule = st.session_state.meal_schedule
        exact_total = sum(item.estimated_price for item in plan.shopping_list)

        # 1) 캘린더 위 장보기 리스트
        badges = "".join([
            f"<span style='display:inline-block; background:white; border:1px solid #a5d6a7; border-radius:8px; padding:6px 12px; margin:4px; font-size:0.95em;'>"
            f"🥬 <b>{i.name}</b> <span style='color:#2e7d32;'>({i.amount})</span> "
            f"<span style='color:#777; font-size:0.85em;'>· 약 {i.estimated_price:,}원</span></span>"
            for i in plan.shopping_list
        ])
        st.markdown(f"""
        <div style="border:1px solid #81c784; border-radius:12px; padding:18px; background:#f1f8e9; margin:15px 0;">
            <h4 style="margin-top:0; color:#2e7d32;">🛒 이번 주 장보기 리스트 (필요한 재료와 양)</h4>
            <div>{badges}</div>
        </div>
        """, unsafe_allow_html=True)

        # 2) 클릭 가능한 캘린더 + 오른쪽 총 가격
        with st.container(border=True):
            st.markdown(f"#### 📅 [{saved_goal}] 이번 주 자취생 맞춤 식단 캘린더 *(메뉴를 클릭하면 상세 레시피 화면으로 이동합니다)*")

            cal_col, price_col = st.columns([6.5, 1.5])
            plan_by_day = {p.day.replace("요일", "").strip(): p for p in plan.daily_plans}
            all_selected = set(m for meals in saved_schedule.values() for m in meals)

            with cal_col:
                hdr_cols = st.columns([1] + [1]*7)
                hdr_cols[0].markdown("<div class='cal-header'>구분</div>", unsafe_allow_html=True)
                for i, d in enumerate(DAYS):
                    hdr_cols[i+1].markdown(f"<div class='cal-header'>{d}</div>", unsafe_allow_html=True)

                for m_key, attr, m_label in [("아침", "breakfast", "🌅 아침"), ("점심", "lunch", "☀️ 점심"), ("저녁", "dinner", "🌙 저녁")]:
                    if m_key not in all_selected:
                        continue
                    row_cols = st.columns([1] + [1]*7)
                    row_cols[0].markdown(f"<div class='cal-meal-label'>{m_label}</div>", unsafe_allow_html=True)
                    for i, d in enumerate(DAYS):
                        p = plan_by_day.get(d)
                        menu = getattr(p, attr).strip() if p else "-"
                        if m_key not in saved_schedule.get(d, []) or not menu or menu == "-":
                            row_cols[i+1].button("-", key=f"btn_{m_key}_{d}", disabled=True, use_container_width=True)
                        else:
                            if row_cols[i+1].button(menu, key=f"btn_{m_key}_{d}", use_container_width=True):
                                st.session_state.selected_menu = menu
                                st.session_state.detail_dish = None
                                st.session_state.page = "page_3_detail"
                                st.rerun()

            with price_col:
                diff = saved_budget - exact_total
                diff_html = f"<div style='color:#2e7d32; font-size:0.88em;'>예산 대비 {diff:,}원 절약!</div>" if diff >= 0 else f"<div style='color:#d32f2f; font-size:0.88em;'>예산 대비 {abs(diff):,}원 초과</div>"
                st.markdown(f"""
                <div style="border:1px solid #81c784; border-radius:10px; background:#f1f8e9; padding:20px 10px; text-align:center; margin-top:4px;">
                    <div style="font-weight:bold; color:#1b5e20; border-bottom:1px solid #c8e6c9; padding-bottom:6px; margin-bottom:10px;">💰 총 가격</div>
                    <div style="font-size:0.85em; color:#555;">주간 총 예상 식비</div>
                    <div style="font-size:1.35em; font-weight:bold; color:#2e7d32; margin:6px 0;">{exact_total:,}원</div>
                    {diff_html}
                </div>
                """, unsafe_allow_html=True)

            st.info(f"💡 **자취생 살림 팁:** {plan.tip}")

# ==========================================
# [화면 3-상세] 식단표에서 클릭한 메뉴의 상세 레시피
# ==========================================
elif st.session_state.page == "page_3_detail":
    b1, b2, _ = st.columns([1.2, 1.2, 4])
    with b1:
        st.button("⬅️ 식단표로 돌아가기", on_click=go_page, args=("page_3",), use_container_width=True)
    with b2:
        st.button("🏠 처음 화면으로", on_click=go_page, args=("home",), use_container_width=True)

    menu = st.session_state.selected_menu
    st.subheader(f"🍳 [{menu}] 상세 레시피")

    if st.session_state.detail_dish is None and menu:
        prompt = f"""
        [선택한 메뉴]: {menu}
        [식단 목적]: {st.session_state.meal_goal}
        자취생이 집에서 그대로 따라 하기만 하면 완벽하게 만들 수 있도록 '{menu}'의 아주 상세한 레시피(재료 손질법, 불 세기, 조리 시간, 상태 변화 포함), 영양 정보, 쓰레기 처리 가이드(이유 없이 배출처만)를 작성해 주세요.
        """
        with st.spinner(f"👨‍🍳 [{menu}] 자취생 맞춤 초상세 레시피를 작성하고 있습니다..."):
            try:
                res = client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="당신은 자취생에게 요리를 아주 친절하고 상세하게 알려주는 전문 셰프입니다.",
                        response_mime_type="application/json",
                        response_schema=Dish,
                    ),
                )
                st.session_state.detail_dish = res.parsed or Dish.model_validate_json(res.text)
            except Exception as e:
                st.error(f"❌ 오류가 발생했습니다: {e}")

    if st.session_state.detail_dish:
        render_dish_card(st.session_state.detail_dish, open_by_default=True)
