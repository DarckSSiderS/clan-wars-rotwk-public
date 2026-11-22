import api from './api';

const path = cycleId => `/campaign/cycles/${encodeURIComponent(cycleId)}/interception/review`;
const send = async (cycleId, dispatchId, action, payload) => (
  await api.post(`${path(cycleId)}/${action}`, payload, { params: { dispatch_id: dispatchId } })
).data;

export const cycleInterceptionReviewService = {
  async read(cycleId, dispatchId, config) {
    return (await api.get(path(cycleId), { ...config, params: { dispatch_id: dispatchId } })).data;
  },
  review: (cycleId, dispatchId, payload) => send(cycleId, dispatchId, 'contributions', payload),
  adjust: (cycleId, dispatchId, payload) => send(cycleId, dispatchId, 'adjustments', payload),
  preview: (cycleId, dispatchId, payload) => send(cycleId, dispatchId, 'outcome/preview', payload),
  confirm: (cycleId, dispatchId, payload) => send(cycleId, dispatchId, 'outcome/confirm', payload),
};
