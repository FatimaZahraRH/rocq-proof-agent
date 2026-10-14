(* Suite « bases » : arithmétique et listes, propriétés classiques.

   Sert d'échauffement et de point de comparaison. Attention : la bibliothèque
   standard de Rocq contient déjà des lemmes proches (ex. app_nil_r), qu'un agent
   peut légitimement invoquer. Les scores sur cette suite sont donc à lire comme
   un plafond « facile » ; la suite memory_isolation, qui repose sur des
   définitions propres au projet, est le vrai test.
*)

From Coq Require Import List Arith Lia.
Import ListNotations.

Fixpoint count (x : nat) (l : list nat) : nat :=
  match l with
  | [] => 0
  | y :: t => (if Nat.eqb x y then 1 else 0) + count x t
  end.

(* @theorem add_zero_right | facile *)
Theorem add_zero_right : forall n : nat, n + 0 = n.
Proof.
  induction n as [| k IH]; simpl.
  - reflexivity.
  - rewrite IH. reflexivity.
Qed.

(* @theorem add_succ_right | facile *)
Theorem add_succ_right : forall n m : nat, n + S m = S (n + m).
Proof.
  induction n as [| k IH]; intros m; simpl.
  - reflexivity.
  - rewrite IH. reflexivity.
Qed.

(* @theorem add_comm_bench | moyen *)
Theorem add_comm_bench : forall n m : nat, n + m = m + n.
Proof.
  intros n m. lia.
Qed.

(* @theorem mul_zero_right | facile *)
Theorem mul_zero_right : forall n : nat, n * 0 = 0.
Proof.
  induction n as [| k IH]; simpl.
  - reflexivity.
  - exact IH.
Qed.

(* @theorem app_nil_right_bench | facile *)
Theorem app_nil_right_bench : forall (l : list nat), l ++ [] = l.
Proof.
  induction l as [| x t IH]; simpl.
  - reflexivity.
  - rewrite IH. reflexivity.
Qed.

(* @theorem app_assoc_bench | moyen *)
Theorem app_assoc_bench : forall (l1 l2 l3 : list nat),
  (l1 ++ l2) ++ l3 = l1 ++ (l2 ++ l3).
Proof.
  induction l1 as [| x t IH]; intros l2 l3; simpl.
  - reflexivity.
  - rewrite IH. reflexivity.
Qed.

(* @theorem app_length_bench | moyen *)
Theorem app_length_bench : forall (l1 l2 : list nat),
  length (l1 ++ l2) = length l1 + length l2.
Proof.
  induction l1 as [| x t IH]; intros l2; simpl.
  - reflexivity.
  - rewrite IH. reflexivity.
Qed.

(* @theorem rev_length_bench | moyen *)
Theorem rev_length_bench : forall (l : list nat), length (rev l) = length l.
Proof.
  (* Lemme local : évite de dépendre du nom app_length / length_app,
     qui a changé selon les versions de Rocq. *)
  assert (Happ : forall l1 l2 : list nat,
             length (l1 ++ l2) = length l1 + length l2).
  { induction l1 as [| y t IH]; intros l2; simpl; [reflexivity | rewrite IH; reflexivity]. }
  induction l as [| x t IH]; simpl.
  - reflexivity.
  - rewrite Happ. simpl. rewrite IH. lia.
Qed.

(* @theorem count_app | moyen *)
Theorem count_app : forall (x : nat) (l1 l2 : list nat),
  count x (l1 ++ l2) = count x l1 + count x l2.
Proof.
  intros x. induction l1 as [| y t IH]; intros l2; simpl.
  - reflexivity.
  - rewrite IH. lia.
Qed.

(* @theorem count_le_length | difficile *)
Theorem count_le_length : forall (x : nat) (l : list nat),
  count x l <= length l.
Proof.
  intros x. induction l as [| y t IH]; simpl.
  - lia.
  - destruct (Nat.eqb x y); simpl; lia.
Qed.
