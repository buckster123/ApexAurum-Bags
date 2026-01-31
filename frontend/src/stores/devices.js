import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'

export const useDevicesStore = defineStore('devices', () => {
  const devices = ref([])
  const loading = ref(false)
  const error = ref(null)

  // Shown once after creation/rotation - cleared when user dismisses
  const newDeviceToken = ref(null)
  const newConfigJson = ref(null)

  async function fetchDevices() {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get('/api/v1/devices/')
      devices.value = data
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to load devices'
    } finally {
      loading.value = false
    }
  }

  async function createDevice(deviceName, deviceType = 'apex_pocket') {
    error.value = null
    try {
      const { data } = await api.post('/api/v1/devices/', {
        device_name: deviceName,
        device_type: deviceType
      })
      // data includes: id, device_name, device_type, token, token_prefix, config_json, created_at
      newDeviceToken.value = data.token
      newConfigJson.value = data.config_json
      // Refresh the list
      await fetchDevices()
      return data
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to create device'
      throw e
    }
  }

  async function revokeDevice(deviceId) {
    error.value = null
    try {
      await api.post(`/api/v1/devices/${deviceId}/revoke`)
      await fetchDevices()
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to revoke device'
      throw e
    }
  }

  async function rotateToken(deviceId) {
    error.value = null
    try {
      const { data } = await api.post(`/api/v1/devices/${deviceId}/rotate`)
      newDeviceToken.value = data.token
      newConfigJson.value = data.config_json
      await fetchDevices()
      return data
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to rotate token'
      throw e
    }
  }

  async function deleteDevice(deviceId) {
    error.value = null
    try {
      await api.delete(`/api/v1/devices/${deviceId}`)
      await fetchDevices()
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to delete device'
      throw e
    }
  }

  async function updateDevice(deviceId, deviceName) {
    error.value = null
    try {
      await api.patch(`/api/v1/devices/${deviceId}`, {
        device_name: deviceName
      })
      await fetchDevices()
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to update device'
      throw e
    }
  }

  function clearNewToken() {
    newDeviceToken.value = null
    newConfigJson.value = null
  }

  return {
    devices,
    loading,
    error,
    newDeviceToken,
    newConfigJson,
    fetchDevices,
    createDevice,
    revokeDevice,
    rotateToken,
    deleteDevice,
    updateDevice,
    clearNewToken
  }
})
