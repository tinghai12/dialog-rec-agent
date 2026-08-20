/**
 * 高德地图 JS API 按需加载。
 *
 * Key 与安全密钥放在 frontend/.env（VITE_AMAP_KEY / VITE_AMAP_SECURITY），已被 gitignore。
 * 没配 Key 时 loadAMap() 抛错，调用方据此降级到内置简易底图。
 */
const KEY = import.meta.env.VITE_AMAP_KEY || ''
const SECURITY = import.meta.env.VITE_AMAP_SECURITY || ''
const VERSION = '2.0'

let loading = null

export function hasAMapKey() {
  return !!KEY
}

export function loadAMap(plugins = ['AMap.Driving', 'AMap.MoveAnimation', 'AMap.Geocoder']) {
  if (window.AMap) return Promise.resolve(window.AMap)
  if (loading) return loading

  if (!KEY) {
    return Promise.reject(new Error('未配置 VITE_AMAP_KEY'))
  }

  // 2021-12 之后申请的 Key 必须先设置安全���钥，否则接口会返回 INVALID_USER_SCODE
  if (SECURITY) {
    window._AMapSecurityConfig = { securityJsCode: SECURITY }
  }

  loading = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=${VERSION}&key=${KEY}&plugin=${plugins.join(',')}`
    script.async = true
    script.onload = () => (window.AMap ? resolve(window.AMap) : reject(new Error('高德 JS API 加载异常')))
    script.onerror = () => {
      loading = null
      reject(new Error('高德 JS API 加载失败，请检查网络或 Key'))
    }
    document.head.appendChild(script)
  })
  return loading
}

/** 地址 → 经纬度。失败返回 null，由调用方决定是否继续。 */
export async function geocode(address, city = '') {
  const AMap = await loadAMap()
  return new Promise((resolve) => {
    const geocoder = new AMap.Geocoder({ city: city || '全国' })
    geocoder.getLocation(address, (status, result) => {
      if (status === 'complete' && result.geocodes?.length) {
        const { lng, lat } = result.geocodes[0].location
        resolve({ lng, lat, formatted: result.geocodes[0].formattedAddress })
      } else {
        resolve(null)
      }
    })
  })
}

/** 驾车路径规划，返回 [[lng,lat], ...]。 */
export async function planRoute(origin, dest) {
  const AMap = await loadAMap()
  return new Promise((resolve, reject) => {
    const driving = new AMap.Driving({ policy: AMap.DrivingPolicy?.LEAST_TIME ?? 0, showTraffic: false })
    driving.search(new AMap.LngLat(origin[0], origin[1]), new AMap.LngLat(dest[0], dest[1]), (status, result) => {
      if (status !== 'complete' || !result.routes?.length) {
        return reject(new Error('路径规划失败'))
      }
      const points = []
      for (const step of result.routes[0].steps || []) {
        for (const p of step.path || []) points.push([p.lng, p.lat])
      }
      points.length >= 2 ? resolve(points) : reject(new Error('路径点不足'))
    })
  })
}
