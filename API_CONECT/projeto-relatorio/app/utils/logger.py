import os
import json
from datetime import datetime
from typing import Dict, Any, Optional

class ProcessLogger:
    def __init__(self, process_id: str = None):
        self.process_id = process_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.start_time = datetime.now()
        self.current_step = "INICIO"
        self.steps_log = []
    
    def _log(self, level: str, message: str, step: str = None, extra: Dict[str, Any] = None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        step = step or self.current_step
        
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "step": step,
            "message": message,
            "process_id": self.process_id
        }
        
        if extra:
            log_entry.update(extra)
        
        # Log estruturado para arquivo (se necessário)
        if os.getenv("LOG_TO_FILE", "false").lower() == "true":
            with open(f"logs/process_{self.process_id}.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        
        # Log visual no console
        emoji = {
            "INFO": "🔹",
            "SUCCESS": "✅", 
            "WARNING": "⚠️",
            "ERROR": "❌",
            "STEP": "🚀",
            "DB": "🗄️",
            "WEB": "🌐",
            "DATA": "📊",
            "FILE": "📁"
        }.get(level, "🔹")
        
        print(f"[{timestamp}] {emoji} [{step}] {message}")
        
        # Armazena para histórico
        self.steps_log.append(log_entry)
    
    def step(self, step_name: str, message: str = None):
        """Define uma nova etapa do processo"""
        self.current_step = step_name
        if message:
            self._log("STEP", f"INICIANDO: {message}", step_name)
        else:
            self._log("STEP", f"INICIANDO: {step_name}", step_name)
    
    def info(self, message: str, extra: Dict[str, Any] = None):
        """Log informativo"""
        self._log("INFO", message, extra=extra)
    
    def success(self, message: str, extra: Dict[str, Any] = None):
        """Log de sucesso"""
        self._log("SUCCESS", message, extra=extra)
    
    def warning(self, message: str, extra: Dict[str, Any] = None):
        """Log de aviso"""
        self._log("WARNING", message, extra=extra)
    
    def error(self, message: str, extra: Dict[str, Any] = None):
        """Log de erro"""
        self._log("ERROR", message, extra=extra)
    
    def db(self, message: str, extra: Dict[str, Any] = None):
        """Log específico para operações de banco"""
        self._log("DB", message, extra=extra)
    
    def web(self, message: str, extra: Dict[str, Any] = None):
        """Log específico para operações web/playwright"""
        self._log("WEB", message, extra=extra)
    
    def data(self, message: str, extra: Dict[str, Any] = None):
        """Log específico para processamento de dados"""
        self._log("DATA", message, extra=extra)
    
    def file(self, message: str, extra: Dict[str, Any] = None):
        """Log específico para operações de arquivo"""
        self._log("FILE", message, extra=extra)
    
    def finish(self, success: bool = True, summary: Dict[str, Any] = None):
        """Finaliza o processo e mostra resumo"""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        status = "✅ SUCESSO" if success else "❌ FALHA"
        self._log("STEP", f"PROCESSO FINALIZADO: {status} em {duration:.2f}s", "FINALIZACAO")
        
        if summary:
            self._log("INFO", f"RESUMO: {json.dumps(summary, ensure_ascii=False, indent=2)}", "FINALIZACAO")
        
        return {
            "process_id": self.process_id,
            "success": success,
            "duration_seconds": duration,
            "steps_count": len(self.steps_log),
            "summary": summary
        }

# Funções de conveniência para compatibilidade
def info(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔹 {msg}")

def success(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ {msg}")

def warn(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⚠️ {msg}")

def error(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ {msg}")
