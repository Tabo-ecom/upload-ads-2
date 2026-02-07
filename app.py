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
# 🤖 2. AGENTE DE IA
# ==============================================================================
def generar_copy_ia(api_key, nombre_producto, descripcion):
    if not api_key: return {"headline": "¡Pide y Paga en Casa!", "body": "⚠️ Falta API Key."}
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
# 🛠️ 3. CLASE DE GESTIÓN FACEBOOK
# ==============================================================================
class FBAdsManager:
    def __init__(self, token):
        self.token = token

    def get_my_ad_accounts(self):
        url = f"{BASE_URL}/me/adaccounts"
        params = {"access_token": self.token, "fields": "name,account_id,currency", "limit": 100}
        res = requests.get(url, params=params).json()
        return {f"{acc.get('name')} ({acc.get('currency')})": f"act_{acc['account_id']}" for acc in res.get('data', [])} if "data" in res else {}

    def upload_media(self, ad_account_id, file_obj=None, file_url=None, file_type="image/jpeg"):
        endpoint = "advideos" if "video" in file_type else "adimages"
        url = f"{BASE_URL}/{ad_account_id}/{endpoint}"
        params = {'access_token': self.token}
        
        # Subida Local vs URL
        if file_obj:
            # Importante: seek(0) para poder leer el archivo múltiples veces (para múltiples cuentas)
            file_obj.seek(0)
            files = {'file': (file_obj.name, file_obj.read(), file_obj.type)}
            res = requests.post(url, params=params, files=files).json()
        elif file_url:
            params['url'] = file_url 
            res = requests.post(url, params=params).json()
        
        if "error" in res: raise Exception(f"Media Error: {res['error'].get('message')}")

        if "video" in file_type:
            video_id = res['id']
            while True:
                status_res = requests.get(f"{BASE_URL}/{video_id}", params={'fields': 'status,picture', 'access_token': self.token}).json()
                status = status_res.get('status', {}).get('video_status')
                if status == 'ready': return {"video_id": video_id, "thumbnail_url": status_res.get('picture')}
                if status == 'error': raise Exception("FB rechazó el video.")
                time.sleep(3)
        
        return {"image_hash": list(res['images'].values())[0]['hash']}

def create_ad_logic(account_id, adset_id, media_data, url, head, body, cta, page_id, token, ad_name_file):
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
        "name": f"Creative - {ad_name_file}",
        "object_story_spec": json.dumps(object_story_spec), "access_token": token
    }).json()
    
    if "id" not in res_cr: raise Exception(f"Error Creativo: {res_cr.get('error', {}).get('message')}")

    res_ad = requests.post(f"{BASE_URL}/{account_id}/ads", data={
        "name": ad_name_file,
        "adset_id": adset_id,
        "creative": json.dumps({"creative_id": res_cr['id']}), "status": "PAUSED", "access_token": token
    }).json()
    
    if "id" not in res_ad: raise Exception(f"Error Anuncio: {res_ad.get('error', {}).get('message')}")
    return True

# ==============================================================================
# 🖥️ 4. INTERFAZ STREAMLIT
# ==============================================================================
st.set_page_config(page_title="GL Ads Launcher PRO", layout="wide")
st.title("🚀 GL Group Ads Launcher (Multi-Cuentas)")

fb_secret = st.secrets.get("FB_ACCESS_TOKEN", "")
oa_secret = st.secrets.get("OPENAI_API_KEY", "")

with st.sidebar:
    st.header("⚙️ Configuración")
    fb_token = st.text_input("FB Access Token", value=fb_secret, type="password")
    oa_token = st.text_input("OpenAI API Key", value=oa_secret, type="password")
    
    acc_names_sel = []
    accounts = {}
    
    if fb_token:
        try:
            manager = FBAdsManager(fb_token)
            accounts = manager.get_my_ad_accounts()
            if accounts:
                # CAMBIO: Multiselect para Cuentas
                acc_names_sel = st.multiselect("🎯 Cuentas Publicitarias (Selecciona varias)", list(accounts.keys()))
        except:
            st.error("Token inválido")

if not acc_names_sel:
    st.info("👈 Selecciona al menos una cuenta publicitaria para iniciar.")
    st.stop()

c1, c2 = st.columns([1, 1.2])

with c1:
    st.subheader("1. Configuración de Campaña")
    marcas_sel = st.multiselect("Marcas/Tiendas (Países)", list(STORE_CONFIG.keys()))
    
    col_d1, col_d2 = st.columns(2)
    fecha_inicio = col_d1.date_input("Fecha Inicio", value=datetime.now() + timedelta(days=1))
    genero_sel = col_d2.selectbox("Género", ["Todos", "Hombres", "Mujeres"])
    
    producto = st.text_input("Producto", "PRODUCTO").upper()
    referencia_ia = st.text_area("Descripción IA", height=70)
    url_producto = st.text_input("🔗 URL Destino")
    
    st.divider()
    tipo_puja = st.radio("Estrategia", ["ABO (Clásico)", "CBO (Escalado)", "TESTEO_CREATIVOS"])
    
    if tipo_puja == "TESTEO_CREATIVOS":
        st.info("💰 Presupuesto por CADA Creativo.")
        presupuesto = st.number_input("Valor Individual", value=30000)
    else:
        presupuesto = st.number_input("Presupuesto Total", value=40000)

with c2:
    st.subheader("2. Creativos")
    
    tab_local, tab_nube = st.tabs(["📂 Archivos Locales", "☁️ Enlaces Directos"])
    files_to_process = []
    
    with tab_local:
        archivos_local = st.file_uploader("Arrastra aquí", type=['jpg', 'png', 'mp4'], accept_multiple_files=True)
        if archivos_local:
            for f in archivos_local:
                clean_name = f.name.rsplit('.', 1)[0]
                final_name = f"{clean_name} - {producto}"
                files_to_process.append({"type": "file", "obj": f, "mime": f.type, "name": final_name})
    
    with tab_nube:
        urls_text = st.text_area("URLs (uno por línea)", height=100)
        if urls_text:
            for i, url in enumerate(urls_text.split('\n')):
                if url.strip():
                    mime = "video/mp4" if ".mp4" in url else "image/jpeg"
                    final_name = f"Enlace {i+1} - {producto}"
                    files_to_process.append({"type": "url", "url": url.strip(), "mime": mime, "name": final_name})

    if st.button("✨ Generar Copy con IA"):
        if not oa_token:
            st.error("❌ Falta API Key OpenAI.")
        else:
            with st.spinner("IA trabajando..."):
                ai = generar_copy_ia(oa_token, producto, referencia_ia)
                st.session_state['ai_h'] = ai.get('headline', '')
                st.session_state['ai_b'] = ai.get('body', '')

    h_final = st.text_input("Headline", value=st.session_state.get('ai_h', "¡Pide hoy y Paga en Casa!"))
    b_final = st.text_area("Copy", value=st.session_state.get('ai_b', ""), height=150)
    cta = st.selectbox("CTA", ["ORDER_NOW", "SHOP_NOW"])

st.markdown("---")

if st.button("🚀 LANZAR EN TODAS LAS CUENTAS", type="primary", use_container_width=True):
    if not marcas_sel or not files_to_process or not url_producto:
        st.error("❌ Faltan datos.")
    else:
        status_main = st.empty()
        url_final = f"https://{url_producto}" if not url_producto.startswith("http") else url_producto
        
        # Fecha 05:00 AM
        start_dt = datetime.combine(fecha_inicio, dt_time(5, 0, 0))
        start_time_unix = int(start_dt.timestamp())
        
        # Género
        target_genders = []
        if genero_sel == "Hombres": target_genders = [1]
        elif genero_sel == "Mujeres": target_genders = [2]

        # ======================================================================
        # BUCLE MAESTRO: ITERAR POR CADA CUENTA PUBLICITARIA SELECCIONADA
        # ======================================================================
        for acc_name in acc_names_sel:
            current_acc_id = accounts[acc_name]
            st.markdown(f"## 📡 Procesando Cuenta: **{acc_name}**")
            
            try:
                # BUCLE PAÍSES DENTRO DE LA CUENTA
                for marca in marcas_sel:
                    cfg = STORE_CONFIG[marca]
                    pais = cfg['country']
                    st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;➡️ Configurando {pais}...")

                    # 1. CAMPAÑA
                    c_name = f"{pais} - {producto} - {tipo_puja[:4]} - {datetime.now().strftime('%d/%m')}"
                    p_camp = { 'name': c_name, 'objective': 'OUTCOME_SALES', 'status': 'PAUSED', 'special_ad_categories': '[]', 'access_token': fb_token }
                    
                    if "CBO" in tipo_puja:
                        p_camp['daily_budget'] = int(presupuesto)
                        p_camp['bid_strategy'] = 'LOWEST_COST_WITHOUT_CAP'
                    
                    res_c = requests.post(f"{BASE_URL}/{current_acc_id}/campaigns", data=p_camp).json()
                    if "id" not in res_c: raise Exception(f"Error Campaña {pais}: {res_c.get('error', {}).get('message')}")
                    camp_id = res_c['id']

                    # CONFIG ADSET
                    attribution = json.dumps([{"event_type": "CLICK_THROUGH", "window_days": 7}, {"event_type": "VIEW_THROUGH", "window_days": 1}])
                    targeting_base = {'geo_locations': {'countries': [cfg['country_code']]}, 'age_min': 18, 'age_max': 65}
                    if target_genders: targeting_base['genders'] = target_genders

                    # ESTRATEGIA A: TESTEO
                    if tipo_puja == "TESTEO_CREATIVOS":
                        for idx, item in enumerate(files_to_process):
                            st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Subiendo '{item['name']}' a {acc_name}...")
                            
                            # SUBIDA MEDIA (Se sube de nuevo para cada cuenta, es obligatorio)
                            media_data = manager.upload_media(current_acc_id, file_obj=item.get("obj"), file_url=item.get("url"), file_type=item["mime"])
                            
                            p_as = {
                                'name': f"{pais} - TEST {idx+1} ({item['name']})", 
                                'campaign_id': camp_id, 'status': 'PAUSED',
                                'targeting': json.dumps(targeting_base),
                                'start_time': start_time_unix,
                                'billing_event': 'IMPRESSIONS', 'optimization_goal': 'OFFSITE_CONVERSIONS',
                                'promoted_object': json.dumps({'pixel_id': cfg['pixelId'], 'custom_event_type': 'PURCHASE'}),
                                'destination_type': 'WEBSITE', 'attribution_spec': attribution,
                                'bid_strategy': 'LOWEST_COST_WITHOUT_CAP', 'daily_budget': int(presupuesto),
                                'access_token': fb_token
                            }
                            res_as = requests.post(f"{BASE_URL}/{current_acc_id}/adsets", data=p_as).json()
                            if "id" not in res_as: raise Exception(f"Fallo AdSet: {res_as.get('error',{}).get('message')}")
                            
                            create_ad_logic(current_acc_id, res_as['id'], media_data, url_final, h_final, b_final, cta, cfg['pageId'], fb_token, item['name'])
                            time.sleep(1)

                    # ESTRATEGIA B: CLÁSICO
                    else:
                        p_as = {
                            'name': f"{pais} - OPEN", 'campaign_id': camp_id, 'status': 'PAUSED',
                            'targeting': json.dumps(targeting_base),
                            'start_time': start_time_unix,
                            'billing_event': 'IMPRESSIONS', 'optimization_goal': 'OFFSITE_CONVERSIONS',
                            'promoted_object': json.dumps({'pixel_id': cfg['pixelId'], 'custom_event_type': 'PURCHASE'}),
                            'destination_type': 'WEBSITE', 'attribution_spec': attribution,
                            'bid_strategy': 'LOWEST_COST_WITHOUT_CAP', 'access_token': fb_token
                        }
                        if "ABO" in tipo_puja: p_as['daily_budget'] = int(presupuesto)
                        
                        res_as = requests.post(f"{BASE_URL}/{current_acc_id}/adsets", data=p_as).json()
                        if "id" not in res_as: raise Exception(f"Fallo AdSet: {res_as.get('error',{}).get('message')}")
                        
                        for idx, item in enumerate(files_to_process):
                            st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Subiendo '{item['name']}' a {acc_name}...")
                            media_data = manager.upload_media(current_acc_id, file_obj=item.get("obj"), file_url=item.get("url"), file_type=item["mime"])
                            create_ad_logic(current_acc_id, res_as['id'], media_data, url_final, h_final, b_final, cta, cfg['pageId'], fb_token, item['name'])
                            time.sleep(1)

                    st.success(f"✅ {pais} completado en {acc_name}")
            
            except Exception as e:
                st.error(f"❌ Error en cuenta {acc_name}: {str(e)}")
            
            st.divider() # Separador entre cuentas

        st.balloons()
        status_main.success("🎉 ¡PROCESO MULTI-CUENTA FINALIZADO!")
