import React, { useState, useRef } from 'react';
import { AddAPhotoOutlined } from '@mui/icons-material';
import { showSuccess, showError } from '../utils/notifications';
import { apiFetch } from '../services/apiFetch';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const AvatarUpload = ({ onAvatarUpdate }) => {
  const { getLocalizedText: t } = useLocalizationContext();
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileSelect = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    // Проверяем тип файла (разрешаем все типы изображений включая GIF)
    if (!file.type.startsWith('image/')) {
      showError(t('avatar_choose_image'));
      return;
    }

    // Проверяем размер файла (максимум 5MB)
    if (file.size > 5 * 1024 * 1024) {
      showError(t('avatar_file_too_large'));
      return;
    }

    await uploadAvatar(file);
  };

  const uploadAvatar = async (file) => {
    setIsUploading(true);
    
    try {
      const formData = new FormData();
      formData.append('avatar', file);

      const response = await apiFetch('/api/v1/users/avatar', {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        showSuccess(t('avatar_upload_success'));
        onAvatarUpdate(data.avatar_url);
      } else {
        const errorData = await response.json();
        console.error('Upload error:', errorData);
        showError(errorData.detail || t('avatar_upload_error'));
      }
    } catch (error) {
      console.error('Error uploading avatar:', error);
      showError(t('avatar_upload_error'));
    } finally {
      setIsUploading(false);
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <>
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        accept="image/*"
        style={{ display: 'none' }}
      />
      <button 
        type="button"
        className="avatar-upload-btn" 
        onClick={handleUploadClick}
        disabled={isUploading}
        title={t('avatar_change')}
        aria-label={t('avatar_change')}
      >
        {isUploading ? (
          <div className="spinner-border spinner-border-sm text-white" role="status">
            <span className="visually-hidden">{t('common_loading')}</span>
          </div>
        ) : (
          <>
            <AddAPhotoOutlined className="avatar-upload-icon" aria-hidden="true" />
            <span>{t('avatar_change')}</span>
          </>
        )}
      </button>
    </>
  );
};

export default AvatarUpload; 
