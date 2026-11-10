import { afterAll, afterEach, beforeAll, expect, test } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

import {
  InvalidArgumentError,
  Template,
  TemplateNotFoundError,
} from '../../src'
import { TEST_API_KEY, apiUrl } from '../setup'

const requestedTemplateIDs: string[] = []
let templateOverrides: Record<string, unknown> = {}

const build = {
  buildID: '22222222-2222-2222-2222-222222222222',
  status: 'ready',
  cpuCount: 2,
  maxCpuCount: 4,
  memoryMB: 1024,
  diskSizeMB: 5120,
  createdAt: '2026-11-05T15:00:00Z',
  updatedAt: '2026-11-05T15:01:00Z',
  finishedAt: '2026-11-05T15:01:00Z',
}

const server = setupServer(
  http.get(apiUrl('/templates/aliases/:alias'), ({ params }) => {
    if (params.alias === 'missing') {
      return HttpResponse.json(
        { code: 404, message: 'Template not found' },
        { status: 404 }
      )
    }
    return HttpResponse.json({ templateID: 'template-id', public: false })
  }),
  http.get(apiUrl('/templates/:templateID'), ({ params }) => {
    requestedTemplateIDs.push(params.templateID as string)
    return HttpResponse.json({
      templateID: 'template-id',
      buildID: build.buildID,
      cpuCount: 2,
      maxCpuCount: 4,
      memoryMB: 1024,
      diskSizeMB: 5120,
      public: false,
      aliases: ['resizable'],
      names: ['team/resizable'],
      createdAt: '2026-11-05T14:00:00Z',
      updatedAt: '2026-11-05T15:01:00Z',
      createdBy: null,
      lastSpawnedAt: null,
      spawnCount: 0,
      buildCount: 2,
      envdVersion: '0.2.4',
      buildStatus: 'ready',
      builds: [
        build,
        {
          ...build,
          buildID: '11111111-1111-1111-1111-111111111111',
          maxCpuCount: undefined,
          finishedAt: undefined,
          status: 'error',
        },
      ],
      ...templateOverrides,
    })
  })
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))

afterAll(() => server.close())

afterEach(() => {
  requestedTemplateIDs.length = 0
  templateOverrides = {}
  server.resetHandlers()
})

test('getInfo resolves a name to its ID and returns CPU counts', async () => {
  const info = await Template.getInfo('resizable', { apiKey: TEST_API_KEY })

  expect(requestedTemplateIDs).toEqual(['template-id'])
  expect(info).toMatchObject({
    templateId: 'template-id',
    buildId: build.buildID,
    names: ['team/resizable'],
    cpuCount: 2,
    maxCpuCount: 4,
    memoryMB: 1024,
  })
  expect(info.builds[0]).toEqual({
    buildId: build.buildID,
    status: 'ready',
    cpuCount: 2,
    maxCpuCount: 4,
    memoryMB: 1024,
    diskSizeMB: 5120,
    createdAt: new Date(build.createdAt),
    finishedAt: new Date(build.finishedAt),
  })
  expect(info.builds[1].maxCpuCount).toBeUndefined()
  expect(info.builds[1].finishedAt).toBeUndefined()
})

test('getInfo throws for an unknown template', async () => {
  await expect(
    Template.getInfo('missing', { apiKey: TEST_API_KEY })
  ).rejects.toBeInstanceOf(TemplateNotFoundError)
})

test('getInfo rejects tagged names before resolving them', async () => {
  let resolved = false
  server.use(
    http.get(apiUrl('/templates/aliases/:alias'), () => {
      resolved = true
      return HttpResponse.json({ templateID: 'template-id', public: false })
    })
  )

  const error = await Template.getInfo('resizable:v1', {
    apiKey: TEST_API_KEY,
  }).catch((e) => e)
  expect(error).toBeInstanceOf(InvalidArgumentError)
  expect(error.message).toContain("Use Template.getInfo('resizable')")
  expect(resolved).toBe(false)
})

test('getInfo omits default resources when only other tags have ready builds', async () => {
  templateOverrides = {
    buildID: '00000000-0000-0000-0000-000000000000',
    cpuCount: 0,
    maxCpuCount: undefined,
    memoryMB: 0,
    diskSizeMB: 0,
    envdVersion: '',
    buildStatus: 'waiting',
  }
  const info = await Template.getInfo('resizable', { apiKey: TEST_API_KEY })

  expect(info).toMatchObject({
    buildId: undefined,
    cpuCount: undefined,
    maxCpuCount: undefined,
    memoryMB: undefined,
    diskSizeMB: undefined,
    envdVersion: undefined,
  })
  expect(info.builds[0].cpuCount).toBe(2)
})

test('getInfo preserves a fixed-size default after a failed rebuild', async () => {
  templateOverrides = { buildStatus: 'error', maxCpuCount: undefined }
  const info = await Template.getInfo('resizable', { apiKey: TEST_API_KEY })

  expect(info.buildId).toBe(build.buildID)
  expect(info.cpuCount).toBe(2)
  expect(info.maxCpuCount).toBeUndefined()
})
