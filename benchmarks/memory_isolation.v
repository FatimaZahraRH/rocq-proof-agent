(* Suite « isolation mémoire » : propriétés de sécurité sur un modèle de mémoire jouet.

   La mémoire est une liste d'entiers ; [read] et [write] accèdent à une case
   par son indice. On prouve que les accès hors bornes sont inoffensifs, qu'une
   écriture ne touche que sa propre case, et qu'une écriture hors d'une région
   ne modifie pas la région (isolation).

   Format du fichier (lu par src/proof_agent/benchmark.py) :
   - tout ce qui précède le premier marqueur @theorem est le CONTEXTE, donné à l'agent ;
   - chaque bloc « @theorem nom | difficulté » contient l'énoncé et une preuve de
     RÉFÉRENCE. La preuve de référence n'est jamais montrée à l'agent : elle sert
     uniquement à garantir que chaque énoncé est prouvable (voir tests/).
*)

From Coq Require Import List Arith Lia.
Import ListNotations.

Definition mem := list nat.

Fixpoint read (m : mem) (i : nat) : option nat :=
  match m, i with
  | [], _ => None
  | x :: _, 0 => Some x
  | _ :: t, S k => read t k
  end.

Fixpoint write (m : mem) (i : nat) (v : nat) : mem :=
  match m, i with
  | [], _ => []
  | _ :: t, 0 => v :: t
  | x :: t, S k => x :: write t k v
  end.

(* Lecture protégée par un contrôle de bornes explicite. *)
Definition safe_read (m : mem) (i : nat) : option nat :=
  if i <? length m then read m i else None.

(* Une région mémoire = les indices [base, base + size). *)
Definition in_region (base size i : nat) : Prop := base <= i /\ i < base + size.

(* @theorem read_out_of_bounds | facile *)
Theorem read_out_of_bounds : forall (m : mem) (i : nat),
  length m <= i -> read m i = None.
Proof.
  induction m as [| x t IH]; intros i H.
  - reflexivity.
  - destruct i as [| k]; simpl in *.
    + lia.
    + apply IH. lia.
Qed.

(* @theorem read_in_bounds | moyen *)
Theorem read_in_bounds : forall (m : mem) (i : nat),
  i < length m -> exists v, read m i = Some v.
Proof.
  induction m as [| x t IH]; intros i H; simpl in *.
  - lia.
  - destruct i as [| k].
    + exists x. reflexivity.
    + apply IH. lia.
Qed.

(* @theorem safe_read_out_of_bounds | facile *)
Theorem safe_read_out_of_bounds : forall (m : mem) (i : nat),
  length m <= i -> safe_read m i = None.
Proof.
  intros m i H. unfold safe_read.
  destruct (i <? length m) eqn:E.
  - apply Nat.ltb_lt in E. lia.
  - reflexivity.
Qed.

(* @theorem safe_read_some_in_bounds | moyen *)
Theorem safe_read_some_in_bounds : forall (m : mem) (i v : nat),
  safe_read m i = Some v -> i < length m.
Proof.
  intros m i v H. unfold safe_read in H.
  destruct (i <? length m) eqn:E.
  - apply Nat.ltb_lt in E. exact E.
  - discriminate H.
Qed.

(* @theorem write_length | facile *)
Theorem write_length : forall (m : mem) (i v : nat),
  length (write m i v) = length m.
Proof.
  induction m as [| x t IH]; intros i v.
  - reflexivity.
  - destruct i as [| k]; simpl.
    + reflexivity.
    + rewrite IH. reflexivity.
Qed.

(* @theorem write_out_of_bounds_noop | facile *)
Theorem write_out_of_bounds_noop : forall (m : mem) (i v : nat),
  length m <= i -> write m i v = m.
Proof.
  induction m as [| x t IH]; intros i v H.
  - reflexivity.
  - destruct i as [| k]; simpl in *.
    + lia.
    + rewrite IH by lia. reflexivity.
Qed.

(* @theorem write_read_same | moyen *)
Theorem write_read_same : forall (m : mem) (i v : nat),
  i < length m -> read (write m i v) i = Some v.
Proof.
  induction m as [| x t IH]; intros i v H; simpl in *.
  - lia.
  - destruct i as [| k]; simpl.
    + reflexivity.
    + apply IH. lia.
Qed.

(* @theorem write_read_other | moyen *)
Theorem write_read_other : forall (m : mem) (i j v : nat),
  i <> j -> read (write m i v) j = read m j.
Proof.
  induction m as [| x t IH]; intros i j v H.
  - reflexivity.
  - destruct i as [| k], j as [| l]; simpl.
    + contradiction.
    + reflexivity.
    + reflexivity.
    + apply IH. intro E. apply H. rewrite E. reflexivity.
Qed.

(* @theorem write_write_same | moyen *)
Theorem write_write_same : forall (m : mem) (i v w : nat),
  write (write m i v) i w = write m i w.
Proof.
  induction m as [| x t IH]; intros i v w.
  - reflexivity.
  - destruct i as [| k]; simpl.
    + reflexivity.
    + rewrite IH. reflexivity.
Qed.

(* @theorem write_outside_region_isolated | difficile *)
Theorem write_outside_region_isolated : forall (m : mem) (base size i j v : nat),
  in_region base size j -> ~ in_region base size i ->
  read (write m i v) j = read m j.
Proof.
  intros m base size i j v Hj Hi.
  assert (Hneq : i <> j).
  { intro E. subst. contradiction. }
  clear Hj Hi base size.
  revert i j Hneq.
  induction m as [| x t IH]; intros i j Hneq.
  - reflexivity.
  - destruct i as [| k], j as [| l]; simpl.
    + contradiction.
    + reflexivity.
    + reflexivity.
    + apply IH. intro E. apply Hneq. rewrite E. reflexivity.
Qed.

(* @theorem safe_read_after_write_other | difficile *)
Theorem safe_read_after_write_other : forall (m : mem) (i j v : nat),
  i <> j -> safe_read (write m i v) j = safe_read m j.
Proof.
  intros m i j v H. unfold safe_read.
  assert (Hlen : forall (m' : mem) (i' v' : nat),
             length (write m' i' v') = length m').
  { induction m' as [| x t IH]; intros i' v'.
    - reflexivity.
    - destruct i' as [| k]; simpl; [reflexivity | rewrite IH; reflexivity]. }
  rewrite Hlen.
  destruct (j <? length m).
  - revert i j H. induction m as [| x t IH]; intros i j H.
    + reflexivity.
    + destruct i as [| k], j as [| l]; simpl.
      * contradiction.
      * reflexivity.
      * reflexivity.
      * apply IH. intro E. apply H. rewrite E. reflexivity.
  - reflexivity.
Qed.
