import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

class R2Storage:
    def __init__(self):
        self.account_id = os.getenv('R2_ACCOUNT_ID')
        self.access_key_id = os.getenv('R2_ACCESS_KEY_ID')
        self.secret_access_key = os.getenv('R2_SECRET_ACCESS_KEY')
        self.bucket_name = os.getenv('R2_BUCKET_NAME')
        self.public_url = os.getenv('R2_PUBLIC_URL')
        
        # Проверка что все переменные загружены
        if not all([self.account_id, self.access_key_id, self.secret_access_key, self.bucket_name]):
            raise ValueError("Не все R2 переменные окружения установлены!")
        
        # Создаем S3-клиент для R2
        self.client = boto3.client(
            's3',
            endpoint_url=f'https://{self.account_id}.r2.cloudflarestorage.com',
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=Config(signature_version='s3v4', region_name='auto')
        )
        print(f"✅ R2 клиент инициализирован для bucket: {self.bucket_name}")
    
    def upload_file(self, file_path: str, object_key: str, content_type: str = 'image/png') -> str:
        """
        Загружает файл в R2
        
        Args:
            file_path: путь к локальному файлу
            object_key: имя файла в bucket (например: 'images/card_123.png')
            content_type: MIME тип файла
            
        Returns:
            Публичная ссылка на файл
        """
        try:
            with open(file_path, 'rb') as f:
                self.client.upload_fileobj(
                    f,
                    self.bucket_name,
                    object_key,
                    ExtraArgs={
                        'ContentType': content_type,
                        'CacheControl': 'public, max-age=31536000',
                    }
                )
            
            url = f"{self.public_url}/{object_key}"
            print(f"✅ Файл загружен: {object_key}")
            return url
            
        except ClientError as e:
            print(f"❌ Ошибка загрузки в R2: {e}")
            raise
        except FileNotFoundError:
            print(f"❌ Файл не найден: {file_path}")
            raise
    
    def delete_file(self, object_key: str) -> bool:
        """Удаляет файл из R2"""
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=object_key)
            print(f"✅ Файл удален: {object_key}")
            return True
        except ClientError as e:
            print(f"❌ Ошибка удаления из R2: {e}")
            return False
    
    def file_exists(self, object_key: str) -> bool:
        """Проверяет существование файла в R2"""
        try:
            self.client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError:
            return False


# Singleton instance
r2_storage = R2Storage()