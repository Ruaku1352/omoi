import { useEffect, useRef, useState } from 'react'
import momoBase from '../assets/mascot/momo-base.png'
import momoBlink from '../assets/mascot/momo-blink.png'
import momoTalk1 from '../assets/mascot/momo-talk1.png'
import momoTalk2 from '../assets/mascot/momo-talk2.png'
import momoHappy from '../assets/mascot/momo-happy.png'
import './MomoMascot.css'

const CONFIG = {
  BLINK_MIN: 2400,
  BLINK_MAX: 5200,
  BLINK_HOLD: 140,
  TYPE_SPEED: 55,
  MOUTH_MS: 150,
  LOOP: true,
}

const MESSAGES = [
  'こんにちは、わたしは "もも"。使ってくれてありがとう。',
  'ちなみに、この子（わたし）もomoiのマスコットなんだよ。',
  'あなたの思い出を、もっとかんたんに形にするのが目標なんだ。',
  'いま、選んでもらった写真から大事な要素を見つけてるところ。',
  '奥行きのあるレイヤーに分けて、立体的なアートワークを組み立ててるよ。',
  'もうすこしで完成——楽しみにしててね。',
]

type Frame = 'base' | 'blink' | 'talk1' | 'talk2' | 'happy'
const FRAME_SRC: Record<Frame, string> = {
  base: momoBase,
  blink: momoBlink,
  talk1: momoTalk1,
  talk2: momoTalk2,
  happy: momoHappy,
}

export default function MomoMascot() {
  const [frame, setFrame] = useState<Frame>('base')
  const [lineIndex, setLineIndex] = useState(0)
  const [displayedText, setDisplayedText] = useState('')
  // 打ち終わって「タップ待ち」になっているか。次のセリフへは自動では進まない
  // （2026-09-04、まなみん指示: ユーザーがタップするまで次の説明を言わないようにする）
  const [waitingForTap, setWaitingForTap] = useState(false)
  const isTypingRef = useRef(false)
  const timers = useRef<number[]>([])
  const skipRef = useRef<() => void>(() => {})

  const clearTimers = () => {
    timers.current.forEach((id) => window.clearTimeout(id))
    timers.current = []
  }
  const addTimer = (fn: () => void, ms: number) => {
    const id = window.setTimeout(fn, ms)
    timers.current.push(id)
    return id
  }

  // まばたき
  useEffect(() => {
    let cancelled = false
    const scheduleBlink = () => {
      const delay = CONFIG.BLINK_MIN + Math.random() * (CONFIG.BLINK_MAX - CONFIG.BLINK_MIN)
      addTimer(() => {
        if (cancelled || isTypingRef.current) return scheduleBlink()
        setFrame('blink')
        addTimer(() => {
          if (!cancelled && !isTypingRef.current) setFrame('base')
          scheduleBlink()
        }, CONFIG.BLINK_HOLD)
      }, delay)
    }
    scheduleBlink()
    return () => { cancelled = true }
  }, [])

  // セリフのタイプライター表示 → タップで次へ（自動送りはしない）
  useEffect(() => {
    clearTimers()
    isTypingRef.current = true
    setWaitingForTap(false)
    setDisplayedText('')
    const line = MESSAGES[lineIndex]
    let mouthToggle = false
    let charI = 0

    const goNextLine = () => {
      if (lineIndex < MESSAGES.length - 1) setLineIndex((i) => i + 1)
      else if (CONFIG.LOOP) setLineIndex(0)
    }

    const finishTyping = () => {
      clearTimers()
      isTypingRef.current = false
      charI = line.length
      setDisplayedText(line)
      const isLast = lineIndex === MESSAGES.length - 1
      setFrame(isLast ? 'happy' : 'base')
      // 打ち終わったらここで止めて、タップされるまで次のセリフへ進まない
      skipRef.current = goNextLine
      setWaitingForTap(true)
    }

    skipRef.current = finishTyping // タイプ中は「タップで一気に表示」

    const mouthTick = () => {
      mouthToggle = !mouthToggle
      setFrame(mouthToggle ? 'talk1' : 'talk2')
      addTimer(mouthTick, CONFIG.MOUTH_MS)
    }
    mouthTick()

    const typeTick = () => {
      charI += 1
      setDisplayedText(line.slice(0, charI))
      if (charI < line.length) addTimer(typeTick, CONFIG.TYPE_SPEED)
      else finishTyping()
    }
    addTimer(typeTick, CONFIG.TYPE_SPEED)

    return () => clearTimers()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lineIndex])

  return (
    <div className="momo" onClick={() => skipRef.current()} role="button" tabIndex={0}>
      <img className="momo-sprite" src={FRAME_SRC[frame]} alt="もも" />
      <div className="momo-bubble">
        <p className="momo-bubble-text">{displayedText}</p>
        {waitingForTap && (
          <p
            className="momo-bubble-text"
            style={{ margin: '4px 0 0', opacity: 0.55, fontSize: '0.75em', textAlign: 'right' }}
          >
            ▼ タップで次へ
          </p>
        )}
      </div>
    </div>
  )
}