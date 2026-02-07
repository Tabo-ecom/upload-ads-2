import streamlit as st
import requests
import json
import time
from datetime import datetime, timedelta, time as dt_time

# ==============================================================================
# 🧠 1. CONFIGURACIÓN MAESTRA
# ==============================================================================
STORE_CONFIG = {
    'TABO': { 'pixelId': '4560468307512217', 'pageId': '243219548872531', 'currency': 'COP', 'country': 'COLOMBIA', 'country_code': 'CO' },
    'LUCENT': { 'pixelId': '563993102229371', 'pageId': '113244918233996', 'currency': 'COP', 'country': 'COLOMBIA', 'country_code': 'CO' },
    'ESSENTIALS': { 'pixelId': '464847386087738', 'pageId': '102680836073183', 'currency': 'COP', 'country': 'COLOMBIA', 'country_code': 'CO' },
    'ECUADOR': { 'pixelId': '118188614559337', 'pageId': '105888269081575', 'currency': 'USD', 'country': 'ECUADOR', 'country_code': 'EC' },
    'GUATEMALA': { 'pixelId': '1388416526052294', 'pageId': '837350399464084', 'currency': 'GTQ', 'country': 'GUATEMALA', 'country_code': 'GT' }
}

API_VERSION = "v22.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# ==============================================================================
# 🤖 2. AGENTE DE IA (OPENAI)
# ==============================================================================
def generar_copy_ia(api_key, nombre_producto, descripcion):
    if not api_key: return {"headline": "¡Pide y Paga en Casa!", "body": "⚠️ Falta la API Key de OpenAI."}
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    prompt = f"""Actúa como experto en Dropshipping. Producto: {nombre_producto}. Contexto: {descripcion}.
    Genera un Headline (max 40 chars) y un Body persuasivo con emojis.
    Responde solo JSON: {{'headline': '...', 'body': '...'}}"""
    try:
        res = requests.post(url, headers=headers, json={
            "model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}],
            "response_format": { "type": "json_object" }
        }).json()
        return json.loads(res['choices'][0]['message']['content'])
    except Exception as e:
        return {"headline": "Error IA", "body": str(e)}

# ==============================================================================
# 🛠️ 3. CLASE DE GESTIÓN Y FUNCIONES
# ==============================================================================
class FBAdsManager:
    def __init__(self, token):
        self.token = token

    def get_my_ad_accounts(self):
        url = f"{BASE_URL}/me/adaccounts"
        params = {"access_token": self.token, "fields": "name,account_id,currency", "limit": 100}
        res = requests.get(url, params=params).json()
        return {f"{acc.get('name')} ({acc.get('currency')})": f"act_{acc['account_id']}" for acc in res.get('data', [])} if "data" in res else {}

    # Función inteligente: Soporta Archivo Local o URL
    def upload_media(self, ad_account_id, file_obj=None, file_url=None, file_type="image/jpeg"):
        endpoint = "advideos" if "video" in file_type else "adimages"
        url = f"{BASE_URL}/{ad_account_id}/{endpoint}"
        params = {'access_token': self.token}
        
        # Caso 1: Archivo Local (Streamlit Uploader)
        if file_obj:
            files = {'file': (file_obj.name, file_obj.getvalue(), file_obj.type)}
            res = requests.post(url, params=params, files=files).json()
        
        # Caso 2: URL Directa (Drive/Nube)
        elif file_url:
            # Para URL, Facebook tiene un parámetro específico 'url' o 'file_url'
            params['url'] = file_url 
            res = requests.post(url, params=params).json()
        
        if "error" in res: raise Exception(f"Media Error: {res['error'].get('message')}")

        # Procesamiento si es Video
        if "video" in file_type:
            video_id = res['id']
            while True:
                status_res = requests.get(f"{BASE_URL}/{video_id}", params={'fields': 'status,picture', 'access_token': self.token}).json()
                status = status_res.get('status', {}).get('video_status')
                if status == 'ready': return {"video_id": video_id, "thumbnail_url": status_res.get('picture')}
                if status == 'error': raise Exception("FB rechazó el video.")
                time.sleep(3)
        
        return {"image_hash": list(res['images'].values())[0]['hash']}

def create_ad_logic(account_id, adset_id, media_data, url, head, body, cta, page_id, token, idx, prod_name):
    object_story_spec = {"page_id": page_id}
    if "video_id" in media_data:
        object_story_spec["video_data"] = {
            "video_id": media_data["video_id"], "image_url": media_data["thumbnail_url"],
            "message": body, "title": head, "call_to_action": {"type": cta, "value": {"link": url}}
        }
    else:
        object_story_spec["link_data"] = {
            "image_hash": media_data["image_hash"], "link": url, "message": body, "name": head, "call_to_action": {"type": cta}
        }

    res_cr = requests.post(f"{BASE_URL}/{account_id}/adcreatives", data={
        "name": f"Creative {idx+1} - {prod_name}",
        "object_story_spec": json.dumps(object_story_spec), "access_token": token
    }).json()
    if "id" not in res_cr: raise Exception(f"Error Creativo: {res_cr.get('error', {}).get('message')}")

    res_ad = requests.post(f"{BASE_URL}/{account_id}/ads", data={
        "name": f"AD{idx+1} - {prod_name}", "adset_id": adset_id,
        "creative": json.dumps({"creative_id": res_cr['id']}), "status": "PAUSED", "access_token": token
    }).json()
    if "id" not in res_ad: raise Exception(f"Error Anuncio: {res_ad.get('error', {}).get('message')}")
    return True

# ==============================================================================
# 🖥️ 4. INTERFAZ STREAMLIT
# ==============================================================================
st.set_page_config(page_title="GL Ads Launcher ULTIMATE", layout="wide")
st.title("🚀 GL Group Ads Launcher PRO")

fb_token = st.secrets.get("FB_ACCESS_TOKEN", "")
oa_token = st.secrets.get("OPENAI_API_KEY", "")

with st.sidebar:
    st.header("⚙️ Configuración")
    if not fb_token: fb_token = st.text_input("FB Access Token", type="password")
    
    ad_account_id = None
    if fb_token:
        manager = FBAdsManager(fb_token)
        accounts = manager.get_my_ad_accounts()
        if accounts:
            acc_name = st.selectbox("🎯 Cuenta Publicitaria", list(accounts.keys()))
            ad_account_id = accounts[acc_name]

if not ad_account_id: st.stop()

c1, c2 = st.columns([1, 1.2])

with c1:
    st.subheader("1. Segmentación y Fecha")
    marcas_sel = st.multiselect("Marcas/Tiendas", list(STORE_CONFIG.keys()))
    
    # --- NUEVOS CAMPOS: FECHA Y GÉNERO ---
    col_d1, col_d2 = st.columns(2)
    fecha_inicio = col_d1.date_input("Fecha de Inicio", value=datetime.now() + timedelta(days=1))
    genero_sel = col_d2.selectbox("Género", ["Todos", "Hombres", "Mujeres"])
    
    producto = st.text_input("Producto", "PRODUCTO").upper()
    url_producto = st.text_input("🔗 URL Destino")
    referencia_ia = st.text_area("Descripción IA (Opcional)", height=70)
    
    st.divider()
    tipo_puja = st.radio("Estrategia", ["ABO (Clásico)", "CBO (Escalado)", "TESTEO_CREATIVOS"])
    
    if tipo_puja == "TESTEO_CREATIVOS":
        st.info("💰 Presupuesto por CADA Creativo.")
        presupuesto = st.number_input("Valor", value=30000)
    else:
        presupuesto = st.number_input("Presupuesto Total", value=40000)

with c2:
    st.subheader("2. Creativos (Local o Nube)")
    
    tab_local, tab_nube = st.tabs(["📂 Subir Archivos", "☁️ Enlaces (Drive/Nube)"])
    
    files_to_process = []
    
    with tab_local:
        archivos_local = st.file_uploader("Arrastra archivos aquí", type=['jpg', 'png', 'mp4'], accept_multiple_files=True)
        if archivos_local:
            for f in archivos_local:
                files_to_process.append({"type": "file", "obj": f, "mime": f.type})
    
    with tab_nube:
        st.caption("Pega enlaces directos de videos/imágenes (uno por línea).")
        urls_text = st.text_area("URLs de Archivos", placeholder="https://mi-servidor.com/video1.mp4\nhttps://mi-servidor.com/video2.mp4")
        if urls_text:
            for url in urls_text.split('\n'):
                if url.strip():
                    # Asumimos video si termina en mp4, sino imagen
                    mime = "video/mp4" if ".mp4" in url else "image/jpeg"
                    files_to_process.append({"type": "url", "url": url.strip(), "mime": mime})

    # Generador Copy
    if st.button("✨ Generar Copy IA"):
        with st.spinner("IA Redactando..."):
            ai = generar_copy_ia(oa_token, producto, referencia_ia)
            st.session_state['ai_h'] = ai.get('headline', '')
            st.session_state['ai_b'] = ai.get('body', '')

    h_final = st.text_input("Headline", value=st.session_state.get('ai_h', "¡Pide hoy y Paga en Casa!"))
    b_final = st.text_area("Copy", value=st.session_state.get('ai_b', ""), height=150)
    cta = st.selectbox("CTA", ["ORDER_NOW", "SHOP_NOW"])

st.markdown("---")

if st.button("🚀 LANZAR CAMPAÑAS", type="primary", use_container_width=True):
    if not marcas_sel or not files_to_process or not url_producto:
        st.error("❌ Faltan datos (Marcas, Creativos o URL).")
    else:
        try:
            status_msg = st.empty()
            url_final = f"https://{url_producto}" if not url_producto.startswith("http") else url_producto
            
            # --- LÓGICA DE FECHA Y HORA (05:00 AM) ---
            # Combinamos la fecha seleccionada con las 5 AM
            start_dt = datetime.combine(fecha_inicio, dt_time(5, 0, 0))
            start_time_unix = int(start_dt.timestamp())
            
            # --- LÓGICA DE GÉNERO ---
            target_genders = [] # Vacío = Todos
            if genero_sel == "Hombres": target_genders = [1]
            elif genero_sel == "Mujeres": target_genders = [2]

            for marca in marcas_sel:
                cfg = STORE_CONFIG[marca]
                pais = cfg['country']
                st.write(f"### 🏗️ {pais}...")

                # 1. CAMPAÑA
                c_name = f"{pais} - {producto} - {tipo_puja[:4]} - {datetime.now().strftime('%d/%m')}"
                p_camp = { 
                    'name': c_name, 'objective': 'OUTCOME_SALES', 'status': 'PAUSED', 
                    'special_ad_categories': '[]', 'access_token': fb_token 
                }
                if "CBO" in tipo_puja:
                    p_camp['daily_budget'] = int(presupuesto)
                    p_camp['bid_strategy'] = 'LOWEST_COST_WITHOUT_CAP'
                
                res_c = requests.post(f"{BASE_URL}/{ad_account_id}/campaigns", data=p_camp).json()
                if "id" not in res_c: raise Exception(f"Error Campaña: {res_c.get('error', {}).get('message')}")
                camp_id = res_c['id']

                # ATRIBUCIÓN
                attribution = json.dumps([{"event_type": "CLICK_THROUGH", "window_days": 7}, {"event_type": "VIEW_THROUGH", "window_days": 1}])
                
                # TARGETING BASE (Con Género)
                targeting_base = {
                    'geo_locations': {'countries': [cfg['country_code']]},
                    'age_min': 18, 'age_max': 65,
                    # Si target_genders está vacío, FB asume TODOS
                }
                if target_genders: targeting_base['genders'] = target_genders

                # --- RAMIFICACIÓN ---
                # OPCIÓN A: TESTEO
                if tipo_puja == "TESTEO_CREATIVOS":
                    for idx, item in enumerate(files_to_process):
                        status_msg.info(f"[{pais}] Conjunto {idx+1}...")
                        
                        # Subida (Local o URL)
                        media_data = manager.upload_media(
                            ad_account_id, 
                            file_obj=item.get("obj"), 
                            file_url=item.get("url"), 
                            file_type=item["mime"]
                        )
                        
                        p_as = {
                            'name': f"{pais} - TEST {idx+1}", 'campaign_id': camp_id, 'status': 'PAUSED',
                            'targeting': json.dumps(targeting_base), # Incluye Género
                            'start_time': start_time_unix, # Incluye Fecha Seleccionada
                            'billing_event': 'IMPRESSIONS', 'optimization_goal': 'OFFSITE_CONVERSIONS',
                            'promoted_object': json.dumps({'pixel_id': cfg['pixelId'], 'custom_event_type': 'PURCHASE'}),
                            'destination_type': 'WEBSITE', 'attribution_spec': attribution,
                            'bid_strategy': 'LOWEST_COST_WITHOUT_CAP', 'daily_budget': int(presupuesto),
                            'access_token': fb_token
                        }
                        res_as = requests.post(f"{BASE_URL}/{ad_account_id}/adsets", data=p_as).json()
                        if "id" not in res_as: raise Exception(f"Fallo AdSet {idx+1}: {res_as.get('error',{}).get('message')}")
                        
                        create_ad_logic(ad_account_id, res_as['id'], media_data, url_final, h_final, b_final, cta, cfg['pageId'], fb_token, idx, producto)
                        time.sleep(1)

                # OPCIÓN B: CLÁSICO
                else:
                    p_as = {
                        'name': f"{pais} - OPEN", 'campaign_id': camp_id, 'status': 'PAUSED',
                        'targeting': json.dumps(targeting_base), # Incluye Género
                        'start_time': start_time_unix, # Incluye Fecha
                        'billing_event': 'IMPRESSIONS', 'optimization_goal': 'OFFSITE_CONVERSIONS',
                        'promoted_object': json.dumps({'pixel_id': cfg['pixelId'], 'custom_event_type': 'PURCHASE'}),
                        'destination_type': 'WEBSITE', 'attribution_spec': attribution,
                        'bid_strategy': 'LOWEST_COST_WITHOUT_CAP', 'access_token': fb_token
                    }
                    if "ABO" in tipo_puja: p_as['daily_budget'] = int(presupuesto)
                    
                    res_as = requests.post(f"{BASE_URL}/{ad_account_id}/adsets", data=p_as).json()
                    if "id" not in res_as: raise Exception(f"Fallo AdSet: {res_as.get('error',{}).get('message')}")
                    
                    for idx, item in enumerate(files_to_process):
                        status_msg.info(f"[{pais}] Anuncio {idx+1}...")
                        media_data = manager.upload_media(
                            ad_account_id, 
                            file_obj=item.get("obj"), 
                            file_url=item.get("url"), 
                            file_type=item["mime"]
                        )
                        create_ad_logic(ad_account_id, res_as['id'], media_data, url_final, h_final, b_final, cta, cfg['pageId'], fb_token, idx, producto)
                        time.sleep(1)

                st.success(f"✅ {pais} Creado.")
            
            st.balloons()
            status_msg.success("🎉 ¡Campañas Programadas!")

        except Exception as e:
            st.error(f"❌ {str(e)}")
