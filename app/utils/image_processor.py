from PIL import Image, ImageOps
import io
import logging

logger = logging.getLogger(__name__)


def process_feedback_image(content: bytes, file_path: str) -> None:
    """Validate and normalize a feedback screenshot without cropping it."""
    with Image.open(io.BytesIO(content)) as source:
        source.load()
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
        image.save(file_path, format="WEBP", quality=88, method=6)


def process_title_image(content: bytes, file_path: str) -> None:
    """Проверяет и сохраняет иконку титула в едином квадратном формате."""
    with Image.open(io.BytesIO(content)) as source:
        source.load()
        image = source.convert("RGBA")
        image = ImageOps.fit(image, (256, 256), method=Image.Resampling.LANCZOS)
        image.save(file_path, format="WEBP", quality=90, method=6)

def process_avatar_image(
    content: bytes,
    file_path: str,
    crop_x: float = None,
    crop_y: float = None,
    crop_width: float = None,
    crop_height: float = None,
    preserve_animation: bool = True,
) -> bool:
    """Обрабатывает изображение аватара с поддержкой обрезки и GIF-анимации"""
    try:
        print(f"Processing avatar image: {file_path}")
        print(f"Content size: {len(content)} bytes")
        
        img = Image.open(io.BytesIO(content))
        print(f"Image opened successfully: {img.format}, {img.size}, {img.mode}")
        
        # Проверяем, является ли это GIF-анимацией
        if not preserve_animation:
            img.seek(0)
            frame = ImageOps.fit(
                img.convert("RGBA"),
                (150, 150),
                method=Image.Resampling.LANCZOS,
            )
            frame.save(file_path, format="WEBP", quality=90, method=6)
            return True

        is_animated_gif = hasattr(img, 'n_frames') and img.n_frames > 1
        
        if is_animated_gif:
            # Для анимированных GIF обрабатываем каждый кадр
            frames = []
            durations = []
            
            for frame_idx in range(img.n_frames):
                img.seek(frame_idx)
                
                # Создаем копию кадра
                frame = img.copy()
                
                # Если указаны параметры обрезки, применяем их
                if all(param is not None for param in [crop_x, crop_y, crop_width, crop_height]):
                    # Вычисляем абсолютные координаты обрезки
                    img_width, img_height = frame.size
                    x = int(crop_x * img_width)
                    y = int(crop_y * img_height)
                    width = int(crop_width * img_width)
                    height = int(crop_height * img_height)
                    
                    # Обрезаем кадр
                    frame = frame.crop((x, y, x + width, y + height))
                
                # Изменяем размер до 150x150 пикселей
                frame = frame.resize((150, 150), Image.Resampling.LANCZOS)
                
                frames.append(frame)
                
                # Сохраняем длительность кадра
                try:
                    durations.append(img.info.get('duration', 100))
                except:
                    durations.append(100)
            
            # Сохраняем анимированный GIF
            if frames:
                frames[0].save(
                    file_path,
                    save_all=True,
                    append_images=frames[1:],
                    duration=durations,
                    loop=0,
                    optimize=True
                )
        else:
            # Для обычных изображений
            # Если указаны параметры обрезки, применяем их
            if all(param is not None for param in [crop_x, crop_y, crop_width, crop_height]):
                # Вычисляем абсолютные координаты обрезки
                img_width, img_height = img.size
                x = int(crop_x * img_width)
                y = int(crop_y * img_height)
                width = int(crop_width * img_width)
                height = int(crop_height * img_height)
                
                # Обрезаем изображение
                img = img.crop((x, y, x + width, y + height))
            
            # Изменяем размер до 150x150 пикселей
            img = img.resize((150, 150), Image.Resampling.LANCZOS)
            
            # Сохраняем обработанное изображение
            img.save(file_path, quality=85, optimize=True)
        
        print(f"Avatar image processed successfully: {file_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        print(f"Error processing image: {e}")
        # Если обработка не удалась, сохраняем оригинал
        if not preserve_animation:
            return False
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        print(f"Original image saved as fallback: {file_path}")
        return False 
