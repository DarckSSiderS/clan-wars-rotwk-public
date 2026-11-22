import React from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Chip,
  TextField,
  Typography,
} from '@mui/material';
import { ExpandMore } from '@mui/icons-material';

const CampaignRuleCategorySection = ({
  category,
  rules,
  values,
  originalValues,
  fieldErrors,
  onChange,
  t,
  defaultExpanded = false,
}) => (
  <Accordion defaultExpanded={defaultExpanded} disableGutters>
    <AccordionSummary expandIcon={<ExpandMore />}>
      <Box className="campaign-rules-category__heading">
        <Typography variant="h6">
          {t(`admin_campaign_rules_category_${category}`, category)}
        </Typography>
        <Chip size="small" label={rules.length} />
      </Box>
    </AccordionSummary>
    <AccordionDetails className="campaign-rules-grid">
      {rules.map((rule) => {
        const changed = Number(values[rule.key]) !== Number(originalValues[rule.key]);
        const error = fieldErrors[rule.key];
        return (
          <Box className={`campaign-rule-field${changed ? ' is-changed' : ''}`} key={rule.key}>
            <Box className="campaign-rule-field__heading">
              <Typography fontWeight={700}>
                {t(rule.label_key, rule.key)}
              </Typography>
              {changed && (
                <Chip
                  size="small"
                  color="warning"
                  label={t('admin_campaign_rules_changed', 'Изменено')}
                />
              )}
            </Box>
            <Typography component="code" variant="caption" color="text.secondary">
              {rule.key}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t(rule.help_key, rule.key)}
            </Typography>
            <TextField
              fullWidth
              type="number"
              size="small"
              value={values[rule.key] ?? ''}
              onChange={(event) => onChange(rule.key, event.target.value)}
              error={Boolean(error)}
              helperText={error || t('admin_campaign_rules_bounds', 'От {min} до {max}', {
                min: rule.minimum,
                max: rule.maximum,
              })}
              label={t(`admin_campaign_rules_unit_${rule.unit}`, rule.unit)}
              slotProps={{
                htmlInput: {
                  min: rule.minimum,
                  max: rule.maximum,
                  step: rule.value_type === 'int' ? 1 : 'any',
                },
              }}
            />
          </Box>
        );
      })}
    </AccordionDetails>
  </Accordion>
);

export default CampaignRuleCategorySection;
