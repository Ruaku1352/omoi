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
 'こんにちは、わたしは "もも"。omoiのマスコットだよ。',
  'omoiって名前、"Our Memories, One Image" の頭文字なんだ。',
  'みんなの思い出を、ひとつの image に重ねるっていう意味。',
  '日本語の「思い」とも掛かってるの、気づいてくれたかな。',
  '選んでもらった写真、いま一枚ずつ見せてもらってるところ。',
  'どこがこの思い出の"主役"かな、って探してるんだ。',
  '見つけたら切り抜いて、奥から手前へ順番に並べていくよ。',
  '平らだった写真が、少しずつ奥行きのある作品になっていく。',
  'できあがったら、くるっと回して好きな角度から見てみてね。',
  '気になるところは、あとから自分で動かして直せるよ。',
  'この作品は、3Dプリンターで本物の形にもできるんだ。',
  'もうすこし。いちばんいい形にしてから渡すね。',]

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