/**
 * Ícones do sistema: UM conjunto (Phosphor, MIT, versão fixa no package.json),
 * UM peso ("regular") e UM tamanho base. Componentes usam estes nomes, nunca
 * SVG desenhado à mão — é o que mantém o traço igual em toda tela.
 * Ver docs/NEXT2026/DESIGN.md (Ícones).
 */
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  BellIcon,
  BellRingingIcon,
  CaretRightIcon,
  CheckCircleIcon,
  CubeIcon,
  DroneIcon,
  MoonIcon,
  PlayIcon,
  PlusIcon,
  PauseIcon,
  ShieldCheckIcon,
  SpeakerHighIcon,
  SpeakerSlashIcon,
  SunIcon,
  WarningIcon,
  WarningOctagonIcon,
  XIcon,
  DownloadSimpleIcon,
  type IconProps,
} from "@phosphor-icons/react";

const BASE: IconProps = { size: 18, weight: "regular", "aria-hidden": true };

export const IconeLua = (p: IconProps) => <MoonIcon {...BASE} {...p} />;
export const IconeSol = (p: IconProps) => <SunIcon {...BASE} {...p} />;
export const IconeSom = (p: IconProps) => <SpeakerHighIcon {...BASE} {...p} />;
export const IconeMudo = (p: IconProps) => <SpeakerSlashIcon {...BASE} {...p} />;
export const IconeSino = (p: IconProps) => <BellIcon {...BASE} {...p} />;
export const IconeSinoAtivo = (p: IconProps) => <BellRingingIcon {...BASE} {...p} />;
export const IconeAvancar = (p: IconProps) => <CaretRightIcon {...BASE} {...p} />;
export const IconeSeta = (p: IconProps) => <ArrowRightIcon {...BASE} {...p} />;
export const IconeVoltar = (p: IconProps) => <ArrowLeftIcon {...BASE} {...p} />;
export const IconeOk = (p: IconProps) => <CheckCircleIcon {...BASE} {...p} />;
export const IconeAviso = (p: IconProps) => <WarningIcon {...BASE} {...p} />;
export const IconeErro = (p: IconProps) => <WarningOctagonIcon {...BASE} {...p} />;
export const IconeFechar = (p: IconProps) => <XIcon {...BASE} {...p} />;
export const IconeTocar = (p: IconProps) => <PlayIcon {...BASE} {...p} />;
export const IconePausar = (p: IconProps) => <PauseIcon {...BASE} {...p} />;
export const IconeBaixar = (p: IconProps) => <DownloadSimpleIcon {...BASE} {...p} />;
export const IconeEscudo = (p: IconProps) => <ShieldCheckIcon {...BASE} {...p} />;
export const IconeCubo = (p: IconProps) => <CubeIcon {...BASE} {...p} />;
export const IconeDrone = (p: IconProps) => <DroneIcon {...BASE} {...p} />;
export const IconeMais = (p: IconProps) => <PlusIcon {...BASE} {...p} />;
