from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
import shutil

app = FastAPI(
    title="VASCULAR.AI API",
    description="AI-планировщик сосудистых операций",
    version="0.1.0"
)

# CORS для GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В production заменить на конкретный URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Пути
DB_PATH = "/tmp/vascular_ai.db"
UPLOAD_DIR = Path("/tmp/uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Инициализация БД
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS studies (
            id TEXT PRIMARY KEY,
            patient_id TEXT,
            study_type TEXT,
            file_path TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operations (
            id TEXT PRIMARY KEY,
            study_id TEXT,
            operation_type TEXT,
            access_point TEXT,
            anesthesia TEXT,
            measurements TEXT,
            protocol_text TEXT,
            status TEXT DEFAULT 'planned',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (study_id) REFERENCES studies (id)
        )
    """)
    
    conn.commit()
    conn.close()

@app.on_event("startup")
async def startup():
    init_db()

@app.get("/")
async def root():
    return {
        "message": "VASCULAR.AI API",
        "version": "0.1.0",
        "status": "running"
    }

@app.post("/upload-dicom")
async def upload_dicom(file: UploadFile = File(...)):
    """Загрузка DICOM файла"""
    try:
        study_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{study_id}.dcm"
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # TODO: Извлечь метаданные из DICOM
        metadata = {
            "filename": file.filename,
            "size": file_path.stat().st_size,
            "content_type": file.content_type
        }
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO studies (id, file_path, metadata) VALUES (?, ?, ?)",
            (study_id, str(file_path), json.dumps(metadata))
        )
        conn.commit()
        conn.close()
        
        return {
            "study_id": study_id,
            "status": "uploaded",
            "metadata": metadata
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create-operation")
async def create_operation(
    study_id: str,
    operation_type: str,
    access_point: str = None,
    anesthesia: str = None
):
    """Создание операции на основе исследования"""
    try:
        operation_id = str(uuid.uuid4())
        
        # Генерация протокола на основе типа операции
        protocol_templates = {
            "aortic_aneurysm_resection": """
ОПЕРАЦИЯ: Резекция аневризмы брюшной аорты с протезированием

ДОСТУП: {access_point}
АНЕСТЕЗИЯ: {anesthesia}

ЭТАПЫ:
1. Доступ в скарповских треугольниках, выделение бедренных артерий
2. Срединная лапаротомия, выделение аневризмы
3. Гепаринизация (5000 ЕД)
4. Пережатие аорты и подвздошных артерий
5. Резекция аневризмы, протезирование «конец-в-конец»
6. Пуск кровотока, контроль гемостаза
7. Дренирование, ушивание раны

ИСПОЛЬЗОВАНО: Протез «Васкутек» 22-11-11 или аналог
""",
            "femoral_thrombectomy": """
ОПЕРАЦИЯ: Тромбэктомия из общей бедренной артерии

ДОСТУП: {access_point}
АНЕСТЕЗИЯ: {anesthesia}

ЭТАПЫ:
1. Доступ в правом/левом скарповском треугольнике
2. Выделение ОБА, контроль гемостаза
3. Гепаринизация (2500-5000 ЕД)
4. Пережатие проксимально и дистально
5. Артериотомия, тромбэктомия катетером Фогарти
6. Промывание, проверка кровотока
7. Зашивание артериотомии нитью пролен 5/0 или 6/0
8. Пуск кровотока, контроль пульсации

ИСПОЛЬЗОВАНО: Катетер Фогарти 4F или 5F
""",
            "varicose_vein_surgery": """
ОПЕРАЦИЯ: Перевязка большой подкожной вены с флебэктомией

ДОСТУП: {access_point}
АНЕСТЕЗИЯ: {anesthesia}

ЭТАПЫ:
1. Доступ в паховой складке (1-2 см ниже устья БПВ)
2. Выделение БПВ, идентификация притоков
3. Лигирование притоков, пересечение БПВ
4. Дистальный доступ на голени, выделение БПВ
5. Инвагинационная флебэктомия (зонд Бэбкока)
6. Минифлебэктомия притоков через проколы
7. Гемостаз, ушивание ран
8. Компрессионное бинтование

НАЗНАЧЕНИЯ: Эластичное бинтование, ранняя активизация
"""
        }
        
        template = protocol_templates.get(
            operation_type, 
            "Операция: {operation_type}\nДоступ: {access_point}\nАнестезия: {anesthesia}"
        )
        
        protocol_text = template.format(
            access_point=access_point or "стандартный",
            anesthesia=anesthesia or "эндотрахеальная"
        )
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO operations 
               (id, study_id, operation_type, access_point, anesthesia, protocol_text) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (operation_id, study_id, operation_type, access_point, anesthesia, protocol_text)
        )
        conn.commit()
        conn.close()
        
        return {
            "operation_id": operation_id,
            "protocol": protocol_text,
            "status": "created"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/operation/{operation_id}")
async def get_operation(operation_id: str):
    """Получение протокола операции"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM operations WHERE id = ?", 
            (operation_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="Operation not found")
        
        columns = [description[0] for description in cursor.description]
        result = dict(zip(columns, row))
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/operations")
async def list_operations():
    """Список всех операций"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, study_id, operation_type, status, created_at FROM operations ORDER BY created_at DESC"
        )
        rows = cursor.fetchall()
        conn.close()
        
        return {
            "operations": [
                {
                    "id": row[0],
                    "study_id": row[1],
                    "operation_type": row[2],
                    "status": row[3],
                    "created_at": row[4]
                }
                for row in rows
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
