import React, { useState } from 'react';
import {
  Avatar,
  IconButton,
  Box,
  CircularProgress,
  Tooltip
} from '@mui/material';
import {
  PhotoCamera,
  Group
} from '@mui/icons-material';
import { clanService } from '../services/clanService';
import { showSuccess, showError } from '../utils/notifications';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const ClanAvatarUpload = ({ clanId, currentAvatarUrl, onAvatarUpdate, size = 80 }) => {
  const { getLocalizedText: t } = useLocalizationContext();
  const [uploading, setUploading] = useState(false);
  const [avatarKey, setAvatarKey] = useState(0); // Для принудительного обновления

  const handleFileChange = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    // Проверяем размер файла (максимум 5MB)
    if (file.size > 5 * 1024 * 1024) {
      showError(t('avatar_file_too_large'));
      return;
    }

    // Проверяем тип файла
    if (!file.type.startsWith('image/')) {
      showError(t('clan_avatar_choose_image'));
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('avatar', file);

      const response = await clanService.uploadAvatar(clanId, formData);
      showSuccess(t('clan_avatar_upload_success'));
      
      if (onAvatarUpdate) {
        onAvatarUpdate(response.avatar_url);
      }
      
      // Принудительно обновляем компонент
      setAvatarKey(prev => prev + 1);
    } catch (error) {
      console.error('Ошибка загрузки аватара:', error);
      showError(t('clan_avatar_upload_error'));
    } finally {
      setUploading(false);
    }
  };

  return (
    <Box position="relative" display="inline-block">
      <Avatar
        key={avatarKey} // Принудительное обновление при изменении ключа
        src={currentAvatarUrl ? `${currentAvatarUrl}?t=${Date.now()}` : '/default-clan-avatar.png'}
        sx={{
          width: size,
          height: size,
          border: '2px solid rgba(255, 255, 255, 0.2)',
          cursor: uploading ? 'not-allowed' : 'pointer'
        }}
      >
        <Group sx={{ fontSize: size * 0.4 }} />
      </Avatar>
      
      {uploading && (
        <Box
          position="absolute"
          top={0}
          left={0}
          right={0}
          bottom={0}
          display="flex"
          alignItems="center"
          justifyContent="center"
          bgcolor="rgba(0, 0, 0, 0.5)"
          borderRadius="50%"
        >
          <CircularProgress size={24} />
        </Box>
      )}
      
      <Tooltip title={t('clan_avatar_change')}>
        <IconButton
          component="label"
          disabled={uploading}
          sx={{
            position: 'absolute',
            bottom: 0,
            right: 0,
            bgcolor: 'rgba(102, 126, 234, 0.9)',
            color: 'white',
            border: '2px solid rgba(255, 255, 255, 0.8)',
            '&:hover': {
              bgcolor: 'rgba(102, 126, 234, 1)',
            },
            width: 32,
            height: 32,
          }}
        >
          <PhotoCamera sx={{ fontSize: 16 }} />
          <input
            type="file"
            hidden
            accept="image/*"
            onChange={handleFileChange}
            disabled={uploading}
          />
        </IconButton>
      </Tooltip>
    </Box>
  );
};

export default ClanAvatarUpload;
