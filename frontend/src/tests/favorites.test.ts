import { describe, it, expect, beforeEach, vi } from 'vitest'

// Mock localStorage before importing favorites
const mockLocalStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  clear: vi.fn(),
  removeItem: vi.fn(),
  length: 0,
  key: vi.fn(),
}

Object.defineProperty(global, 'localStorage', {
  value: mockLocalStorage,
  writable: true,
})

// Now import favorites after mocking localStorage
import { favorites } from '../services/favorites'

describe('favorites service', () => {
  beforeEach(() => {
    // Reset localStorage mocks before each test
    mockLocalStorage.getItem.mockReset()
    mockLocalStorage.setItem.mockReset()
  })

  describe('list', () => {
    it('returns empty array when no favorites exist', () => {
      mockLocalStorage.getItem.mockReturnValue(null)
      const result = favorites.list()
      expect(result).toEqual([])
    })

    it('handles localStorage errors', () => {
      mockLocalStorage.getItem.mockImplementation(() => {
        throw new Error('Storage error')
      })
      const result = favorites.list()
      expect(result).toEqual([])
    })
  })

  describe('has', () => {
    it('returns false when favorite does not exist', () => {
      mockLocalStorage.getItem.mockReturnValue(JSON.stringify([]))
      const result = favorites.has({ videoId: 'video1', segIndex: 0 })
      expect(result).toBe(false)
    })
  })

  describe('toggle', () => {
    it('handles storage errors gracefully when saving', () => {
      mockLocalStorage.getItem.mockReturnValue(JSON.stringify([]))
      mockLocalStorage.setItem.mockImplementation(() => {
        throw new Error('Storage full')
      })

      // Should not throw
      expect(() =>
        favorites.toggle({
          videoId: 'video1',
          segIndex: 0,
          startMs: 1000,
          endMs: 2000,
          text: 'test',
        })
      ).not.toThrow()
    })

    it('calls setItem when toggling', () => {
      mockLocalStorage.getItem.mockReturnValue(JSON.stringify([]))
      mockLocalStorage.setItem.mockImplementation(() => {})

      favorites.toggle({
        videoId: 'video1',
        segIndex: 0,
        startMs: 1000,
        endMs: 2000,
        text: 'test',
      })

      expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
        'favorites:v1',
        expect.any(String)
      )
    })
  })
})
